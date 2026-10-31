import unittest

from mobile_package_lab import (
    LabError,
    balanced_keyword_hits,
    class_name_matches_keyword,
    keyword_hits,
    manifest_components,
    manifest_components_from_xmltree,
    parse_badging,
    parse_edgeone_cookie_challenge,
    parse_signer_report,
    select_apps,
)


class MobilePackageLabTest(unittest.TestCase):
    def test_deferred_apps_cannot_be_acquired_implicitly_or_explicitly(self):
        config = {"apps": [{"key": "wechat"}, {"key": "taobao"}],
                  "collection_approval": {"approved_app_keys": ["wechat", "taobao"], "deferred_app_keys": ["taobao"]}}
        self.assertEqual(select_apps(config, ["all"]), [{"key": "wechat"}])
        with self.assertRaises(LabError):
            select_apps(config, ["taobao"])

    def test_approval_filters_legacy_inventory(self):
        config = {"apps": [{"key": "wechat"}, {"key": "xiaohongshu"}],
                  "collection_approval": {"approved_app_keys": ["wechat"]}}
        self.assertEqual(select_apps(config, ["all"]), [{"key": "wechat"}])
        with self.assertRaises(LabError):
            select_apps(config, ["xiaohongshu"])

    def test_select_apps_rejects_unknown_keys(self):
        config = {"apps": [{"key": "douyin"}, {"key": "wechat"}]}

        with self.assertRaises(LabError):
            select_apps(config, ["missing"])

    def test_parse_badging(self):
        result = parse_badging(
            "package: name='com.example.app' versionCode='42' versionName='1.2.3'\n"
            "sdkVersion:'24'\n"
            "targetSdkVersion:'35'\n"
        )

        self.assertEqual(result["package"], "com.example.app")
        self.assertEqual(result["version_code"], "42")
        self.assertEqual(result["version_name"], "1.2.3")
        self.assertEqual(result["min_sdk"], "24")
        self.assertEqual(result["target_sdk"], "35")

    def test_parse_signer_report(self):
        result = parse_signer_report(
            "Verifies\n"
            "Verified using v1 scheme (JAR signing): true\n"
            "Verified using v2 scheme (APK Signature Scheme v2): true\n"
            "Signer #1 certificate DN: CN=Example\n"
            "Signer #1 certificate SHA-256 digest: AABB\n"
        )

        self.assertTrue(result["verified"])
        self.assertEqual(result["v1"], "true")
        self.assertEqual(result["v2"], "true")
        self.assertEqual(result["signer_dn"], "CN=Example")
        self.assertEqual(result["certificate_sha256"], "AABB")

    def test_manifest_component_filter_input(self):
        manifest = """
        <manifest>
          <application>
            <activity android:name="com.example.OrderActivity" android:exported="true">
            </activity>
            <service android:name="com.example.SyncService">
            </service>
          </application>
        </manifest>
        """

        self.assertEqual(
            manifest_components(manifest),
            [
                {
                    "type": "activity",
                    "name": "com.example.OrderActivity",
                    "exported": "true",
                },
                {
                    "type": "service",
                    "name": "com.example.SyncService",
                    "exported": "unspecified",
                },
            ],
        )

    def test_manifest_components_from_xmltree(self):
        xmltree = """
          E: application (line=1)
            E: activity (line=2)
              A: android:name(0x01010003)="com.example.OrderActivity" (Raw: "com.example.OrderActivity")
              A: android:exported(0x01010010)=true
              E: intent-filter (line=3)
            E: service (line=4)
              A: android:name(0x01010003)="com.example.SyncService" (Raw: "com.example.SyncService")
        """

        self.assertEqual(
            manifest_components_from_xmltree(xmltree),
            [
                {
                    "type": "activity",
                    "name": "com.example.OrderActivity",
                    "exported": "true",
                },
                {
                    "type": "service",
                    "name": "com.example.SyncService",
                    "exported": "unspecified",
                },
            ],
        )

    def test_keyword_hits_deduplicates_and_limits(self):
        self.assertEqual(
            keyword_hits(["我的订单", "我的订单", "退款", "设置"], ["订单", "退款"], 2),
            ["我的订单", "退款"],
        )

    def test_balanced_keyword_hits_keeps_each_domain(self):
        values = ["message.one", "message.two", "message.three", "order.one"]

        self.assertEqual(
            balanced_keyword_hits(values, ["message", "order"], per_keyword=2, limit=4),
            ["message.one", "message.two", "order.one"],
        )

    def test_class_keyword_does_not_treat_recorder_as_order(self):
        self.assertFalse(class_name_matches_keyword("AudioRecorder", "order"))
        self.assertTrue(class_name_matches_keyword("OrderListActivity", "order"))
        self.assertTrue(class_name_matches_keyword("ecom_order_list", "order"))

    def test_parse_edgeone_cookie_challenge(self):
        challenge = b"""<script>
        function a(a){function n(){for(var a={x:'4|2|0|3|1',y:function(a,n){return a+n}},
        n=a.x.split('|'),e=0;;){switch(n[e++]){case'3':t=a.y(t,2671443968);continue}}
        var e={first:31050292,second:218269104,plus:function(a,n){return a+n},third:183432375},t=0;return t}
        document.cookie='__tst_status='+a(0)+'#;';document.cookie='EO_Bot_Ssid=';
        location.href=location.href;
        </script>"""

        self.assertEqual(
            parse_edgeone_cookie_challenge(challenge),
            {"__tst_status": "432751771#", "EO_Bot_Ssid": "2671443968"},
        )


if __name__ == "__main__":
    unittest.main()
