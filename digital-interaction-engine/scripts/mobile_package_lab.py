#!/usr/bin/env python3
"""Acquire and statically inspect approved mobile application packages.

Generated APKs and reports belong under data/package_static, which is ignored by
Git. Static evidence never promotes itself into a reviewed interaction map.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "mobile_app_inventory.json"
DEFAULT_OUTPUT = ROOT / "data" / "package_static"
MYAPP_API = "https://yybadaccess.3g.qq.com/v2/dc_pcyyb_official"
ANDROID_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) "
    "AppleWebKit/537.36 Chrome/128.0 Mobile Safari/537.36"
)

INTERACTION_KEYWORDS = (
    "首页", "我的", "订单", "全部订单", "退款", "退货", "售后", "客服", "支付",
    "购物车", "收藏", "关注", "消息", "搜索", "设置", "地址", "优惠券", "登录",
    "注册", "发布", "拍摄", "直播", "评论", "分享", "转发", "下载", "扫一扫",
    "钱包", "账单", "账户", "安全", "隐私", "确认", "取消", "返回", "下一步",
    "完成", "提交", "删除", "编辑", "更多", "附近", "外卖", "闪购", "商品",
    "店铺", "配送", "收货", "评价", "退款原因", "refund", "order", "payment",
    "checkout", "cart", "profile", "account", "setting", "search", "message",
    "publish", "camera", "live", "comment", "share", "customer", "service",
)

CLASS_KEYWORDS = (
    "order", "refund", "return", "aftersale", "after_sale", "customer", "kefu",
    "payment", "checkout", "cart", "profile", "account", "setting", "search",
    "message", "publish", "camera", "livestream", "live_stream", "comment", "share", "address",
    "coupon", "wallet", "bill", "delivery", "takeout", "shop", "product", "login",
)

ALLOWED_DOWNLOAD_HOST_SUFFIXES = (".qq.com", ".myapp.com", ".360buyimg.com", ".autonavi.com", ".baidu.com", ".ctrip.com",
                                  ".pinduoduo.com", ".pddpic.com", ".alicdn.com", ".guoguo-app.com", ".meituan.net")


class LabError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("apps"), list):
        raise LabError(f"Unsupported inventory schema: {path}")
    return data


def select_apps(config: dict[str, Any], requested: list[str]) -> list[dict[str, Any]]:
    apps = config["apps"]
    approved = config.get("collection_approval", {}).get("approved_app_keys")
    deferred = config.get("collection_approval", {}).get("deferred_app_keys", [])
    if requested and requested != ["all"] and set(requested) & set(deferred):
        raise LabError("App acquisition was deferred by the user")
    apps = [app for app in apps if app["key"] not in deferred]
    if approved is not None:
        if requested and requested != ["all"] and set(requested) - set(approved):
            raise LabError("App is outside the approved collection batch")
        apps = [app for app in apps if app["key"] in approved]
    if not requested or requested == ["all"]:
        return apps
    by_key = {app["key"]: app for app in apps}
    unknown = sorted(set(requested) - set(by_key))
    if unknown:
        raise LabError(f"Unknown app keys: {', '.join(unknown)}")
    return [by_key[key] for key in requested]


def request_json(url: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"User-Agent": ANDROID_USER_AGENT}
    body = None
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers.update(
            {
                "Content-Type": "application/json",
                "Origin": "https://sj.qq.com",
                "Referer": "https://sj.qq.com/",
            }
        )
    request = Request(url, data=body, headers=headers, method="POST" if body else "GET")
    with urlopen(request, timeout=45) as response:
        return json.loads(response.read())


def fetch_myapp_metadata(app: dict[str, Any]) -> dict[str, Any]:
    package = app["android"]["package"]
    payload = {
        "head": {
            "cmd": "dc_pcyyb_official",
            "authInfo": {"businessId": "AuthName"},
            "deviceInfo": {"platformType": 2, "platform": 1},
            "userInfo": {"guid": str(uuid.uuid4())},
            "expSceneIds": "92215",
            "hostAppInfo": {"scene": "game_detail"},
        },
        "body": {
            "bid": "yybhome",
            "offset": 0,
            "size": 10,
            "preview": False,
            "listS": {
                "region": {"repStr": ["CN"]},
                "pkgname": {"repStr": [package]},
            },
            "layout": "yybn_game_basic_info",
        },
    }
    response = request_json(MYAPP_API, payload=payload)
    if response.get("ret") != 0:
        raise LabError(f"MyApp metadata failed for {package}: ret={response.get('ret')}")
    for component in response.get("data", {}).get("components", []):
        if component.get("cardId") != "yybn_game_basic_info":
            continue
        for item in component.get("data", {}).get("itemData", []):
            if item.get("pkg_name") == package:
                return {
                    "source_type": "official_app_store_distribution",
                    "source_name": "Tencent MyApp",
                    "source_listing": app["android"]["listing_url"],
                    "fetched_at": utc_now(),
                    "package": package,
                    "name": item.get("name"),
                    "app_id": item.get("app_id"),
                    "version_name": item.get("version_name"),
                    "download_url": item.get("download_url"),
                    "md5": (item.get("md_5") or "").lower(),
                    "apk_size": int(item.get("apk_size") or 0),
                    "developer": item.get("developer"),
                    "operator": item.get("operator"),
                    "update_time": item.get("update_time"),
                    "description": item.get("description"),
                }
    raise LabError(f"MyApp returned no matching item for {package}")


def fetch_ios_metadata(app: dict[str, Any]) -> dict[str, Any]:
    if not app.get("ios"):
        return {"status": "not_configured", "note": "No verified iOS identifier configured"}
    expected = app["ios"]
    response = request_json(
        f"https://itunes.apple.com/cn/lookup?id={expected['app_store_id']}&country=cn"
    )
    results = response.get("results") or []
    if len(results) != 1:
        raise LabError(f"App Store lookup returned {len(results)} results for {app['key']}")
    item = results[0]
    if item.get("bundleId") != expected["bundle_id"]:
        raise LabError(
            f"Bundle ID mismatch for {app['key']}: "
            f"expected {expected['bundle_id']}, got {item.get('bundleId')}"
        )
    return {
        "source_type": "official_app_store_metadata",
        "source_name": "Apple App Store",
        "fetched_at": utc_now(),
        "app_store_id": item.get("trackId"),
        "bundle_id": item.get("bundleId"),
        "name": item.get("trackName"),
        "version": item.get("version"),
        "seller": item.get("sellerName"),
        "release_date": item.get("currentVersionReleaseDate"),
        "minimum_os_version": item.get("minimumOsVersion"),
        "app_store_url": item.get("trackViewUrl"),
        "artwork_url": item.get("artworkUrl512"),
    }


def ensure_allowed_download_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not any(
        host.endswith(suffix) for suffix in ALLOWED_DOWNLOAD_HOST_SUFFIXES
    ):
        raise LabError(f"Refusing unapproved APK download host: {url}")


def parse_edgeone_cookie_challenge(content: bytes) -> dict[str, str] | None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return None
    markers = ("<script>", "__tst_status=", "EO_Bot_Ssid=", "location.href")
    if not all(marker in text for marker in markers):
        return None
    if len(content) > 64 * 1024:
        raise LabError("Unexpectedly large EdgeOne challenge response")
    status_block = re.search(
        r"var\s+\w+=\{(?P<body>.*?)\},\w+=0;return", text, re.DOTALL
    )
    eo_match = re.search(
        r"case[\"']3[\"']:\w+=.*?\(\w+,(\d+)\);continue", text
    )
    if not status_block or not eo_match:
        raise LabError("Could not parse EdgeOne download challenge")
    status_values = [
        int(value)
        for value in re.findall(r":(\d+)(?=,|$)", status_block.group("body"))
    ]
    if len(status_values) != 3:
        raise LabError("Unexpected EdgeOne challenge constants")
    return {
        "__tst_status": f"{sum(status_values)}#",
        "EO_Bot_Ssid": eo_match.group(1),
    }


def download_apk(metadata: dict[str, Any], destination: Path) -> dict[str, Any]:
    url = metadata.get("download_url") or ""
    ensure_allowed_download_url(url)
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".part")
    temp_path.unlink(missing_ok=True)
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    total = 0
    session = requests.Session()
    resolved_url = url
    try:
        response = session.get(url, stream=True, timeout=(20, 180))
        response.raise_for_status()
        if "text/html" in response.headers.get("Content-Type", ""):
            cookies = parse_edgeone_cookie_challenge(response.content)
            response.close()
            if not cookies:
                raise LabError("Official download returned HTML instead of an APK")
            response = session.get(url, cookies=cookies, stream=True, timeout=(20, 180))
            response.raise_for_status()
        if "text/html" in response.headers.get("Content-Type", ""):
            raise LabError("Official download did not return an APK")
        resolved_url = response.url
        with temp_path.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
        response.close()
        with temp_path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                md5.update(chunk)
                sha256.update(chunk)
                total += len(chunk)
        expected_size = metadata.get("apk_size") or 0
        expected_md5 = (metadata.get("md5") or "").lower()
        if expected_size and total != expected_size:
            raise LabError(f"APK size mismatch: expected {expected_size}, got {total}")
        if expected_md5 and md5.hexdigest() != expected_md5:
            raise LabError(
                f"APK MD5 mismatch: expected {expected_md5}, got {md5.hexdigest()}"
            )
        if not zipfile.is_zipfile(temp_path):
            raise LabError("Downloaded file is not a valid APK/ZIP")
        temp_path.replace(destination)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return {
        "path": str(destination),
        "resolved_url": resolved_url,
        "size": total,
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


def newest_build_tool(name: str) -> Path | None:
    roots = []
    for value in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")):
        if value:
            roots.append(Path(value))
    roots.extend(
        [
            Path.home() / "Library" / "Android" / "sdk",
            Path.home() / "Android" / "Sdk",
        ]
    )
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(root.glob(f"build-tools/*/{name}"))
    return sorted(candidates, reverse=True)[0] if candidates else None


def find_tool(name: str) -> Path:
    override = os.environ.get(name.upper().replace("-", "_") + "_BIN")
    if override and Path(override).is_file():
        return Path(override)
    found = shutil.which(name)
    if found:
        return Path(found)
    if name in {"aapt2", "apksigner", "dexdump"}:
        sdk_tool = newest_build_tool(name)
        if sdk_tool:
            return sdk_tool
    if name == "apkanalyzer":
        roots = [
            Path(os.environ.get("ANDROID_HOME", "")),
            Path.home() / "Library" / "Android" / "sdk",
            Path.home() / "Android" / "Sdk",
        ]
        for root in roots:
            candidate = root / "cmdline-tools" / "latest" / "bin" / name
            if candidate.is_file():
                return candidate
    raise LabError(f"Required tool not found: {name}")


def find_optional_tool(name: str) -> Path | None:
    try:
        return find_tool(name)
    except LabError:
        return None


def command_env() -> dict[str, str]:
    env = os.environ.copy()
    if not env.get("JAVA_HOME"):
        for candidate in (
            Path("/opt/homebrew/opt/openjdk@17"),
            Path("/usr/local/opt/openjdk@17"),
        ):
            if candidate.is_dir():
                env["JAVA_HOME"] = str(candidate)
                env["PATH"] = str(candidate / "bin") + os.pathsep + env.get("PATH", "")
                break
    return env


def run_text(command: list[str], *, check: bool = True) -> str:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=command_env(),
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise LabError(f"Command failed ({result.returncode}): {' '.join(command)}\n{detail}")
    return result.stdout


def parse_badging(text: str) -> dict[str, Any]:
    package_match = re.search(
        r"^package: name='([^']+)' versionCode='([^']*)' versionName='([^']*)'",
        text,
        re.MULTILINE,
    )
    sdk_match = re.search(r"^sdkVersion:'([^']+)'", text, re.MULTILINE)
    target_match = re.search(r"^targetSdkVersion:'([^']+)'", text, re.MULTILINE)
    if not package_match:
        raise LabError("aapt2 did not return APK package metadata")
    return {
        "package": package_match.group(1),
        "version_code": package_match.group(2),
        "version_name": package_match.group(3),
        "min_sdk": sdk_match.group(1) if sdk_match else None,
        "target_sdk": target_match.group(1) if target_match else None,
    }


def parse_signer_report(text: str) -> dict[str, Any]:
    def value(label: str) -> str | None:
        match = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, re.MULTILINE)
        return match.group(1).strip() if match else None

    return {
        "verified": "Verifies" in text,
        "v1": value("Verified using v1 scheme (JAR signing)"),
        "v2": value("Verified using v2 scheme (APK Signature Scheme v2)"),
        "v3": value("Verified using v3 scheme (APK Signature Scheme v3)"),
        "v4": value("Verified using v4 scheme (APK Signature Scheme v4)"),
        "signer_dn": value("Signer #1 certificate DN"),
        "certificate_sha256": value("Signer #1 certificate SHA-256 digest"),
        "certificate_sha1": value("Signer #1 certificate SHA-1 digest"),
        "certificate_md5": value("Signer #1 certificate MD5 digest"),
    }


def normalize_string_pool_line(line: str) -> str | None:
    match = re.match(r"\s*String #\d+\s*:\s*(.*)$", line)
    value = match.group(1).strip() if match else line.strip()
    if not value or len(value) > 240:
        return None
    return value


def keyword_hits(values: Iterable[str], keywords: Iterable[str], limit: int) -> list[str]:
    lowered = tuple(keyword.lower() for keyword in keywords)
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip()
        if not clean or clean in seen:
            continue
        if any(keyword in clean.lower() for keyword in lowered):
            seen.add(clean)
            output.append(clean)
            if len(output) >= limit:
                break
    return output


def balanced_keyword_hits(
    values: Iterable[str], keywords: Iterable[str], *, per_keyword: int, limit: int
) -> list[str]:
    normalized_keywords = tuple(keyword.lower() for keyword in keywords)
    buckets: dict[str, list[str]] = {keyword: [] for keyword in normalized_keywords}
    bucket_seen: dict[str, set[str]] = {keyword: set() for keyword in normalized_keywords}
    for value in values:
        clean = value.strip()
        if not clean:
            continue
        for keyword in normalized_keywords:
            if (
                class_name_matches_keyword(clean, keyword)
                and len(buckets[keyword]) < per_keyword
                and clean not in bucket_seen[keyword]
            ):
                buckets[keyword].append(clean)
                bucket_seen[keyword].add(clean)
    output: list[str] = []
    seen: set[str] = set()
    for keyword in normalized_keywords:
        for value in buckets[keyword]:
            if value in seen:
                continue
            seen.add(value)
            output.append(value)
            if len(output) >= limit:
                return output
    return output


def class_name_matches_keyword(value: str, keyword: str) -> bool:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).lower()
    if "_" in keyword:
        return keyword in expanded
    segments = re.split(r"[._$/:\\-]+", expanded)
    return any(segment.startswith(keyword) for segment in segments if segment)


def manifest_components(manifest: str) -> list[dict[str, str]]:
    component_pattern = re.compile(
        r"<(activity|activity-alias|service|receiver|provider)\b([^>]*)>", re.IGNORECASE
    )
    name_pattern = re.compile(r'android:name="([^"]+)"')
    exported_pattern = re.compile(r'android:exported="([^"]+)"')
    components = []
    for kind, attributes in component_pattern.findall(manifest):
        name = name_pattern.search(attributes)
        if not name:
            continue
        exported = exported_pattern.search(attributes)
        components.append(
            {
                "type": kind.lower(),
                "name": name.group(1),
                "exported": exported.group(1) if exported else "unspecified",
            }
        )
    return components


def manifest_components_from_xmltree(xmltree: str) -> list[dict[str, str]]:
    element_pattern = re.compile(
        r"^(?P<indent>\s*)E: (?P<kind>activity|activity-alias|service|receiver|provider)\b"
    )
    attribute_pattern = re.compile(
        r'^\s*A: .*?:(?P<name>name|exported)\([^)]*\)=(?P<value>"[^"]*"|\w+)'
    )
    components: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    current_indent = 0
    for line in xmltree.splitlines():
        element = element_pattern.match(line)
        line_indent = len(line) - len(line.lstrip())
        if element:
            if current and current.get("name"):
                components.append(current)
            current = {
                "type": element.group("kind").lower(),
                "name": "",
                "exported": "unspecified",
            }
            current_indent = len(element.group("indent"))
            continue
        if current and line.lstrip().startswith("E:") and line_indent <= current_indent:
            if current.get("name"):
                components.append(current)
            current = None
            continue
        if current:
            attribute = attribute_pattern.match(line)
            if attribute:
                value = attribute.group("value").strip('"')
                current[attribute.group("name")] = value
    if current and current.get("name"):
        components.append(current)
    return components


def zip_inventory(apk_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(apk_path) as archive:
        names = archive.namelist()
        dex = [name for name in names if re.fullmatch(r"classes\d*\.dex", name)]
        libraries = [name for name in names if name.startswith("lib/") and name.endswith(".so")]
        assets = [name for name in names if name.startswith("assets/")]
        native_abis = sorted({name.split("/")[1] for name in libraries if name.count("/") >= 2})
    return {
        "file_count": len(names),
        "dex_files": len(dex),
        "native_libraries": len(libraries),
        "native_abis": native_abis,
        "asset_count": len(assets),
        "candidate_assets": keyword_hits(assets, CLASS_KEYWORDS, 500),
    }


def dex_class_candidates(apk_path: Path, apkanalyzer: Path | None) -> list[str]:
    if not apkanalyzer:
        return dex_class_candidates_with_dexdump(apk_path)
    process = subprocess.Popen(
        [str(apkanalyzer), "dex", "packages", "--defined-only", str(apk_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=command_env(),
    )
    assert process.stdout is not None
    class_tree_lines = (
        line.rsplit(None, 1)[-1]
        for line in process.stdout
        if line.lstrip().startswith(("P ", "C "))
    )
    candidates = balanced_keyword_hits(
        class_tree_lines, CLASS_KEYWORDS, per_keyword=100, limit=3000
    )
    _, stderr = process.communicate()
    if process.returncode != 0:
        raise LabError(f"apkanalyzer dex packages failed: {stderr.strip()}")
    return candidates


def dex_class_candidates_with_dexdump(apk_path: Path) -> list[str]:
    dexdump = find_tool("dexdump")
    class_names: list[str] = []
    descriptor_pattern = re.compile(r"Class descriptor\s+: 'L([^;]+);'")
    with zipfile.ZipFile(apk_path) as archive, tempfile.TemporaryDirectory() as temp:
        dex_names = [
            name for name in archive.namelist() if re.fullmatch(r"classes\d*\.dex", name)
        ]
        for dex_name in dex_names:
            dex_path = Path(temp) / dex_name
            with archive.open(dex_name) as source, dex_path.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            process = subprocess.Popen(
                [str(dexdump), "-f", "-n", str(dex_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=command_env(),
            )
            assert process.stdout is not None
            for line in process.stdout:
                match = descriptor_pattern.search(line)
                if match:
                    class_names.append(match.group(1).replace("/", "."))
            _, stderr = process.communicate()
            if process.returncode != 0:
                raise LabError(f"dexdump failed for {dex_name}: {stderr.strip()}")
    return balanced_keyword_hits(
        class_names, CLASS_KEYWORDS, per_keyword=100, limit=3000
    )


def analyze_apk(app: dict[str, Any], apk_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    aapt2 = find_tool("aapt2")
    apksigner = find_tool("apksigner")
    apkanalyzer = (
        None
        if os.environ.get("INTERMAP_USE_DEXDUMP") == "1"
        else find_optional_tool("apkanalyzer")
    )
    badging = parse_badging(run_text([str(aapt2), "dump", "badging", str(apk_path)]))
    expected_package = app["android"]["package"]
    if badging["package"] != expected_package:
        raise LabError(
            f"Package mismatch for {app['key']}: expected {expected_package}, "
            f"got {badging['package']}"
        )
    signer_raw = run_text(
        [str(apksigner), "verify", "--verbose", "--print-certs", str(apk_path)]
    )
    signer = parse_signer_report(signer_raw)
    if not signer["verified"]:
        raise LabError(f"APK signature verification failed: {apk_path}")
    if apkanalyzer:
        manifest = run_text([str(apkanalyzer), "manifest", "print", str(apk_path)])
        components = manifest_components(manifest)
        permissions_raw = run_text(
            [str(apkanalyzer), "manifest", "permissions", str(apk_path)]
        )
    else:
        manifest = run_text(
            [str(aapt2), "dump", "xmltree", str(apk_path), "--file", "AndroidManifest.xml"]
        )
        components = manifest_components_from_xmltree(manifest)
        permissions_raw = run_text([str(aapt2), "dump", "permissions", str(apk_path)])
    strings_raw = run_text([str(aapt2), "dump", "strings", str(apk_path)])
    resource_strings = (
        normalized
        for line in strings_raw.splitlines()
        if (normalized := normalize_string_pool_line(line)) is not None
    )
    component_candidates = [
        component
        for component in components
        if any(
            class_name_matches_keyword(component["name"], keyword)
            for keyword in CLASS_KEYWORDS
        )
    ][:1000]
    return {
        "schema_version": 1,
        "source": "apk_static",
        "status": "pending_review",
        "generated_at": utc_now(),
        "app": {"key": app["key"], "name": app["name"]},
        "provenance": metadata,
        "package": badging,
        "signature": signer,
        "permissions": sorted(
            {line.strip() for line in permissions_raw.splitlines() if line.strip()}
        ),
        "inventory": zip_inventory(apk_path),
        "interaction_candidates": {
            "resource_strings": keyword_hits(resource_strings, INTERACTION_KEYWORDS, 3000),
            "manifest_components": component_candidates,
            "dex_classes": dex_class_candidates(apk_path, apkanalyzer),
        },
        "limitations": [
            "Static package evidence cannot prove current screen coordinates or account-specific UI.",
            "Server-driven, WebView, mini-program, experiment, region, and login-state UI can differ without an APK update.",
            "Candidates must be validated by live GUI/accessibility training before Golden Flow promotion.",
        ],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def hash_file(path: Path) -> dict[str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            md5.update(chunk)
            sha256.update(chunk)
    return {"md5": md5.hexdigest(), "sha256": sha256.hexdigest()}


def app_paths(output: Path, app: dict[str, Any], version: str) -> tuple[Path, Path]:
    safe_version = re.sub(r"[^A-Za-z0-9._-]+", "_", version or "unknown")
    base = output / "android" / app["key"] / safe_version
    return base / f"{app['key']}-{safe_version}.apk", base / "analysis.json"


def refresh_inventory(apps: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    records = []
    for app in apps:
        print(f"[metadata] {app['name']}", flush=True)
        android = fetch_myapp_metadata(app)
        ios = fetch_ios_metadata(app)
        records.append(
            {
                "key": app["key"],
                "name": app["name"],
                "aliases": app.get("aliases", []),
                "android": android,
                "ios": ios,
            }
        )
    result = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "records": records,
    }
    write_json(output / "inventory-current.json", result)
    return result


def run_android(
    apps: list[dict[str, Any]],
    output: Path,
    *,
    analyze: bool,
    keep_existing: bool,
    download_workers: int,
) -> list[dict[str, Any]]:
    prepared = []
    for app in apps:
        print(f"[android] metadata {app['name']}", flush=True)
        metadata = fetch_myapp_metadata(app)
        if not metadata.get("download_url"):
            raise LabError(f"No direct APK URL returned for {app['name']}")
        apk_path, report_path = app_paths(output, app, metadata.get("version_name") or "unknown")
        prepared.append((app, metadata, apk_path, report_path))

    def acquire(item: tuple[dict[str, Any], dict[str, Any], Path, Path]):
        app, metadata, apk_path, report_path = item
        if apk_path.exists() and keep_existing:
            print(f"[android] reuse {apk_path}", flush=True)
            hashes = hash_file(apk_path)
            expected_size = metadata.get("apk_size") or 0
            expected_md5 = (metadata.get("md5") or "").lower()
            if expected_size and apk_path.stat().st_size != expected_size:
                raise LabError(f"Existing APK size does not match metadata: {apk_path}")
            if expected_md5 and hashes["md5"] != expected_md5:
                raise LabError(f"Existing APK MD5 does not match metadata: {apk_path}")
            file_info = {
                "path": str(apk_path),
                "size": apk_path.stat().st_size,
                **hashes,
            }
        else:
            print(f"[android] download {app['name']} {metadata['version_name']}", flush=True)
            file_info = download_apk(metadata, apk_path)
            print(f"[android] downloaded {app['name']}", flush=True)
        metadata["downloaded_file"] = file_info
        write_json(apk_path.parent / "provenance.json", metadata)
        return app, metadata, apk_path, report_path

    with concurrent.futures.ThreadPoolExecutor(max_workers=download_workers) as pool:
        acquired = list(pool.map(acquire, prepared))

    results = []
    for app, metadata, apk_path, report_path in acquired:
        result = {
            "key": app["key"],
            "name": app["name"],
            "version": metadata.get("version_name"),
            "apk_path": str(apk_path),
            "report_path": None,
        }
        if analyze:
            print(f"[android] analyze {app['name']}", flush=True)
            report = analyze_apk(app, apk_path, metadata)
            write_json(report_path, report)
            result["report_path"] = str(report_path)
        results.append(result)
    return results


def analyze_local_apk(
    app: dict[str, Any], apk_path: Path, output: Path, source_url: str
) -> dict[str, Any]:
    if not apk_path.is_file() or not zipfile.is_zipfile(apk_path):
        raise LabError(f"Local APK is not a valid file: {apk_path}")
    aapt2 = find_tool("aapt2")
    badging = parse_badging(run_text([str(aapt2), "dump", "badging", str(apk_path)]))
    if badging["package"] != app["android"]["package"]:
        raise LabError(
            f"Package mismatch for {app['key']}: expected {app['android']['package']}, "
            f"got {badging['package']}"
        )
    hashes = hash_file(apk_path)
    metadata = {
        "source_type": "vendor_official_distribution",
        "source_name": "Official vendor download",
        "source_listing": source_url,
        "fetched_at": utc_now(),
        "package": badging["package"],
        "version_name": badging["version_name"],
        "downloaded_file": {
            "path": str(apk_path),
            "size": apk_path.stat().st_size,
            **hashes,
        },
    }
    _, default_report = app_paths(output, app, badging["version_name"])
    report_path = default_report.with_name("analysis-vendor.json")
    report = analyze_apk(app, apk_path, metadata)
    write_json(report_path, report)
    write_json(report_path.with_name("provenance-vendor.json"), metadata)
    return {
        "key": app["key"],
        "name": app["name"],
        "version": badging["version_name"],
        "apk_path": str(apk_path),
        "report_path": str(report_path),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("inventory", "download-android", "analyze-android", "analyze-local"),
        help="Refresh public metadata, download APKs, or download and analyze APKs.",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--apps",
        nargs="+",
        default=["all"],
        help="Inventory keys, or all.",
    )
    parser.add_argument(
        "--redownload",
        action="store_true",
        help="Download again even when the versioned APK already exists.",
    )
    parser.add_argument(
        "--download-workers",
        type=int,
        default=4,
        help="Concurrent official APK downloads (default: 4).",
    )
    parser.add_argument("--apk", type=Path, help="Local APK for analyze-local.")
    parser.add_argument(
        "--source-url", help="Official vendor source page for analyze-local."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        config = load_config(args.config)
        apps = select_apps(config, args.apps)
        if args.command == "inventory":
            refresh_inventory(apps, args.output)
        elif args.command == "analyze-local":
            if len(apps) != 1 or not args.apk or not args.source_url:
                raise LabError(
                    "analyze-local requires one --apps key, --apk, and --source-url"
                )
            result = analyze_local_apk(apps[0], args.apk, args.output, args.source_url)
            write_json(args.output / "analyze-local-run.json", [result])
        else:
            results = run_android(
                apps,
                args.output,
                analyze=args.command == "analyze-android",
                keep_existing=not args.redownload,
                download_workers=args.download_workers,
            )
            write_json(args.output / f"{args.command}-run.json", results)
        return 0
    except (LabError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
