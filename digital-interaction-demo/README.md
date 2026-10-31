# 小路官网与保留工具

官网阶段版本 `1.1.01`，更新于 2026-10-31。当前已交付 Android 安装包仍为
`1.1.00`，本次没有修改 App 或重新打包。网站阶段号见 `VERSION`；下次 GitHub
阶段备份应使用尚未占用的版本号，不覆盖既有分支和标签。

- `index.html`：产品官网，介绍使用方式、试用场景、操作控制、当前试用范围和数据处理。
- `assets/website.css`、`assets/website.js`：官网样式与三步交互示意。
- `workbench.html`：原有演示与镜像训练工作台，继续使用已有密码保护写入。
- `training-review.html`：旧真机采集复盘，继续使用已有密码读取数据。

官网交互示意不采集屏幕、不调用导航模型、不提交报名信息；当前没有公开安装包下载。
退款示例必须区分订单详情里的“申请退款”和查看已有申请的“退款/售后”。
网站不是固定操作教程，实际指导由 App 根据当前画面生成。

## 本地预览

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory digital-interaction-demo
```

打开 `http://127.0.0.1:8765/`。旧工作台的线上 API 不通过此静态预览代理。

## 部署

```sh
bash digital-interaction-engine/server/deploy_site.sh
```

脚本打包明确列出的静态文件，在服务端准备完整新目录后替换
`/var/www/loop-lulu/intermap`，旧目录保留到 `/var/backups/intermap-site/`。
首页检查失败时恢复旧目录。不会更改 Nginx、服务端代码、鉴权配置或训练/反馈数据。

线上地址：

- 官网 `https://loop-lulu.com/intermap/`
- 旧工作台 `https://loop-lulu.com/intermap/workbench.html`
- 采集复盘 `https://loop-lulu.com/intermap/training-review.html`

## 随 App 进度更新

以 `App/README.md` 和 `digital-interaction-engine/docs/14-consumer-pilot-1.1.md`
核对实际安装包版本、机型验收、支持任务和数据处理。页面底部官网阶段号与
`VERSION`、CSS/JS 查询版本同步递增；试用包版本单独填写，不能把网站上线视为
App 真机验收通过。确认可公开下载后再接入真实安装包地址。
