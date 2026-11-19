# 开发任务看板 · 多人共享版

一个不需要数据库、不需要第三方依赖的任务看板。页面由 Node 服务提供，所有任务实时写入服务器上的 `task.json`，多人同时打开会自动同步。

## 文件说明

| 文件                    | 用途                                                   |
| ----------------------- | ------------------------------------------------------ |
| `index.html`            | 看板页面（前后端逻辑都在这里）                         |
| `task-server.mjs`       | Node 服务，负责页面、任务读写、附件上传、多人同步      |
| `task.json`             | 当前任务数据，首次启动自动创建                         |
| `task.json.bak`         | 每次写入前的自动备份                                   |
| `task-archive.json`     | “彻底删除”的任务归档，默认保留不销毁                   |
| `task-archive.json.bak` | 归档文件的自动备份                                     |
| `task-files/`           | 上传的图片/文档附件                                    |
| `package.json`          | 启动脚本（`npm start`、`npm run pm2:*`），无第三方依赖 |
| `deploy/`               | systemd / PM2 / Nginx 部署示例                         |

> ⚠️ **运行要求：Node.js 18 或更高版本。** 若在 Node 16 下运行可能会遇到兼容性问题，PM2 等现代进程管理工具也会有警告提示。

## 本机试运行

```bash
cd task
node task-server.mjs
# 或者
npm start
```

浏览器打开 <http://127.0.0.1:8765>。

## 放到服务器上给多人使用

### 1. 上传文件

把 `index.html`、`task-server.mjs`、`package.json` 传到服务器同一个目录，例如 `/opt/task-board`。

```bash
sudo mkdir -p /opt/task-board /var/lib/task-board
sudo cp index.html task-server.mjs package.json /opt/task-board/
```

> 如果只用 `node task-server.mjs` 启动、不用 `npm start` 或 PM2 快捷命令，可以不上传 `package.json`；但一起上传不会有副作用。

### 2. 启动

```bash
cd /opt/task-board
HOST=0.0.0.0 PORT=8765 DATA_DIR=/var/lib/task-board node task-server.mjs
```

启动后终端会打印本机地址和局域网地址，例如：

```text
开发任务看板已启动
  本机    http://127.0.0.1:8765
  局域网  http://192.168.1.20:8765
  数据    /var/lib/task-board/task.json
  归档    /var/lib/task-board/task-archive.json
```

其他同事用浏览器打开这个地址即可。记得在服务器防火墙/安全组放行端口：

```bash
sudo ufw allow 8765/tcp          # Ubuntu/Debian
# 或在云厂商安全组里放行 8765 端口
```

### 3. 设置访问密码（公网必做）

不设置密码时，**能访问这个端口的人都能查看、修改、删除任务**。公网部署请务必设置：

```bash
AUTH_USER=admin AUTH_PASS='换成你自己的强密码' \
HOST=0.0.0.0 PORT=8765 DATA_DIR=/var/lib/task-board \
node task-server.mjs
```

设置后浏览器会弹出登录框，输入用户名和密码即可。密码通过 HTTP 明文传输，公网请配合第 5 节的 HTTPS 使用。

### 4. 后台常驻 & 进程守护

#### 推荐方案：使用 PM2（自动重启、崩溃兜底）

相比 `systemd` 或 `nohup`，`PM2` 更适合 Node.js 应用，能在服务崩溃时**秒级自动拉起**，避免出现 Nginx 502。

```bash
# 1. 全局安装 PM2（请确保 Node 版本 >= 18）
npm install -g pm2

# 2. 在 task-server.mjs 所在目录启动，并注入环境变量
cd /www/server/nginx/html/ol-task
HOST=0.0.0.0 PORT=8765 DATA_DIR=/var/lib/task-board \
  pm2 start task-server.mjs --name "task-board"

# 3. 保存当前进程列表并设置开机自启
pm2 save
pm2 startup   # 按提示执行输出的 systemctl enable 命令
```

项目在 `package.json` 里内置了 PM2 快捷命令（PM2 仍需先全局安装），也可以这样启动：

```bash
HOST=0.0.0.0 PORT=8765 DATA_DIR=/var/lib/task-board npm run pm2:start
```

对应的日常操作：

```bash
npm run pm2:status    # 查看状态
npm run pm2:logs      # 实时日志
npm run pm2:restart   # 重启（--update-env，会重新读取环境变量）
npm run pm2:stop      # 停止
npm run pm2:delete    # 从 PM2 列表移除
npm run pm2:save      # 保存进程列表
```

> Windows PowerShell 下环境变量写法不同（例如 `$env:DATA_DIR = "C:\task-data"`），快捷命令本身通用。

**常用运维命令：**

- `pm2 status`：查看运行状态（关注 `↺` 重启次数，如果不断飙升说明代码有崩溃）。
- `pm2 logs task-board`：实时查看日志（按 `Ctrl+C` 退出）。
- `pm2 restart task-board`：重启服务。
- `pm2 monit`：查看 CPU / 内存实时占用。

#### 备选方案：使用 systemd

如果你坚持用系统自带的 `systemd`：

```bash
sudo cp deploy/task-board.service /etc/systemd/system/
sudo cp deploy/task-board.env.example /etc/task-board.env
sudo nano /etc/task-board.env      # 修改密码
sudo useradd -r -s /usr/sbin/nologin taskboard || true
sudo chown -R taskboard:taskboard /var/lib/task-board
sudo systemctl daemon-reload
sudo systemctl enable --now task-board
sudo systemctl status task-board
```

查看日志：

```bash
journalctl -u task-board -f
```

### 5. 域名 + HTTPS（可选，公网推荐）

用 Nginx 反向代理并申请免费证书：

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/task-board
sudo ln -s /etc/nginx/sites-available/task-board /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d task.example.com
```

使用 Nginx 后可以把 `HOST` 改成 `127.0.0.1`，只允许本机代理访问：

```text
HOST=127.0.0.1
PORT=8765
```

### 部署在子路径（例如 `https://example.com/ol/task/`）

不想占用域名根目录时，可以让 Nginx 把整个子路径反向代理给 Node：

1. 把 `index.html`、`task-server.mjs` 放在同一目录并启动服务；
2. 在站点 Nginx 配置里加入 `deploy/nginx-subpath.conf.example` 里的两个 `location`；
3. `nginx -t && nginx -s reload`；
4. 访问 `https://example.com/ol/task/`。

前端会自动把接口请求发到当前页面所在的子路径下（`/ol/task/api/...`、`/ol/task/files/...`），不需要改代码。注意 `/ol/task` 不带末尾斜杠时要跳转到 `/ol/task/`，示例配置里已经处理。

如果页面仍由 Nginx 作为静态文件提供，只想转发接口，也可以只代理这两段：

```nginx
location ^~ /ol/task/api/ {
    proxy_pass http://127.0.0.1:8765/api/;
    client_max_body_size 200m;
    proxy_read_timeout 300s;
}
location ^~ /ol/task/files/ {
    proxy_pass http://127.0.0.1:8765/files/;
    client_max_body_size 200m;
    proxy_read_timeout 300s;
}
```

但更推荐整个子路径都代理给 Node，这样页面版本和接口版本永远一致。

### Windows 服务器

在项目目录打开 PowerShell：

```powershell
$env:HOST = "0.0.0.0"
$env:PORT = "8765"
$env:DATA_DIR = "C:\task-data"
$env:AUTH_USER = "admin"
$env:AUTH_PASS = "换成强密码"
node task-server.mjs
```

注意在 Windows 防火墙中放行 8765 端口。需要开机自启可以用 [NSSM](https://nssm.cc/) 或“任务计划程序”把上面的命令注册为服务。

## 启动 / 停止 / 重启

### 使用 PM2（推荐）

```bash
pm2 start task-board       # 启动（如果是第一次启动用上面的完整命令）
pm2 stop task-board        # 停止
pm2 restart task-board     # 重启
pm2 status                 # 查看状态
pm2 logs task-board        # 实时查看日志
```

### 使用 systemd

```bash
systemctl start task-board      # 启动
systemctl stop task-board       # 停止
systemctl restart task-board    # 重启
systemctl status task-board     # 查看状态
journalctl -u task-board -f     # 实时查看日志
```

### 使用 nohup（不推荐，无崩溃自动拉起）

```bash
# 停止
pkill -f task-server.mjs

# 启动 / 重启（在 task-server.mjs 所在目录执行）
cd /www/server/nginx/html/dist/ol/task
HOST=127.0.0.1 PORT=8765 DATA_DIR=/www/server/nginx/html/dist/ol/task \
  nohup node task-server.mjs > task-server.log 2>&1 &
```

### 什么时候需要重启

| 改动                       | 是否需要重启 Node 服务                                |
| -------------------------- | ----------------------------------------------------- |
| 修改 `task-server.mjs`     | 需要重启                                              |
| 修改 `index.html`          | 不需要，刷新页面即可（Node 每次请求都会重新读取）     |
| 修改 Nginx 配置            | 不需要重启 Node，执行 `nginx -t && nginx -s reload`   |
| 修改 `.env` / PM2 环境变量 | 执行 `pm2 restart task-board --update-env` 或重建进程 |

## 环境变量

| 变量        | 默认值       | 说明                                     |
| ----------- | ------------ | ---------------------------------------- |
| `HOST`      | `0.0.0.0`    | 监听地址；只允许本机访问用 `127.0.0.1`   |
| `PORT`      | `8765`       | 端口                                     |
| `DATA_DIR`  | 脚本所在目录 | 数据目录（`task.json` 和 `task-files/`） |
| `AUTH_USER` | `admin`      | 登录用户名                               |
| `AUTH_PASS` | 空           | 登录密码；为空表示不校验                 |

## 多人同时使用时的行为

- 页面每 4 秒向服务器询问一次版本号，别人改了任务会自动刷新，无需手动刷新页面。
- 任务默认按「状态（未开始 → 开发中 → 已完成）→ 优先级（P0 → P1 → P2）→ 任务号升序」排列，进入页面或刷新后自动生效。
- 任务编号由服务器统一分配，两个人同时点“新增任务”也不会出现重复编号。
- 编辑同一任务时：如果打开编辑框后别人已经改过，保存时会提示你确认是否覆盖。
- 状态切换、拖动排序、移入回收站等操作只改对应字段，不会覆盖别人改的标题/描述。
- “彻底删除”不会真正销毁数据：任务会从看板移除，并写入 `task-archive.json`，附件文件也保留。
- 数据每次改动都会原子写入 `task.json`，并保留上一版 `task.json.bak`；如果主文件损坏，启动时会自动尝试从备份恢复。

## 加载与传输

- 任务列表会先渲染，图片缩略图和附件随后异步加载，首屏不需要等所有附件下载完。
- 缩略图加载中显示统一的转圈动画，加载完成后淡入图片；如果图片本身无法加载（404 或格式损坏），转圈结束并显示“加载失败”占位，鼠标悬停提示“图片加载失败”。
- 首页 HTML 和 `/api/state` JSON 在浏览器支持时自动使用 Brotli 压缩（不支持时回退 gzip）；图片、PDF、ZIP 等附件本身已是压缩格式，不做二次压缩。
- 前面有 Nginx 或 Cloudflare 时通常也会压缩文本响应；Node 返回的响应已经带有 `Content-Encoding`，CDN 一般不会重复压缩。

## 彻底删除的数据 / 找回

在回收站点“彻底删除”后，任务不会丢失：

- 任务记录进入 `task-archive.json`，格式为 `{ "tasks": [ { "archivedAt": ..., "task": {...} } ] }`
- 该任务引用的图片/文档仍保留在 `task-files/`，不会被清理
- 归档只在服务器后台保留，看板页面和接口都不展示，普通用户无感知

需要找回某条任务时：

1. 停止服务；
2. 打开 `task-archive.json`，把对应条目的 `task` 对象复制到 `task.json` 的 `tasks` 数组里；
3. 启动服务。附件 `serverName` 没变，图片/文档会自动恢复。

如果只是想确认某条记录还在，直接搜索 `task-archive.json` 即可，不需要停服务。

## 数据备份

直接备份这三个即可：

```bash
cp /var/lib/task-board/task.json          /backup/task-$(date +%F).json
cp /var/lib/task-board/task-archive.json  /backup/task-archive-$(date +%F).json
cp -r /var/lib/task-board/task-files      /backup/task-files-$(date +%F)
```

建议加一条每日定时备份：

```bash
# crontab -e
0 3 * * * cp /var/lib/task-board/task.json /backup/task-$(date +\%F).json
0 3 * * * cp /var/lib/task-board/task-archive.json /backup/task-archive-$(date +\%F).json
```

## 清空服务器上的测试数据

> 以下操作会删除任务、归档和附件，**不可恢复**。执行前先确认 `task.json` 里没有正式数据。

```bash
# 1. 进入数据目录（改成你自己的 DATA_DIR）
DATA_DIR=/www/server/nginx/html/dist/ol/task
cd "$DATA_DIR"

# 2. 先确认要删的内容
cat task.json
cat task-archive.json 2>/dev/null
ls -la task-files

# 3. 停止服务
pm2 stop task-board 2>/dev/null || systemctl stop task-board 2>/dev/null || pkill -f task-server.mjs

# 4. 清空任务、归档、附件和备份
printf '{\n  "tasks": [],\n  "groups": []\n}\n' > task.json
printf '{\n  "tasks": []\n}\n' > task-archive.json
rm -f task.json.bak task-archive.json.bak task-server.log
rm -rf task-files/*

# 5. 重新启动
pm2 start task-board 2>/dev/null || systemctl restart task-board
# 没有 PM2 / systemd 时改用：
# HOST=127.0.0.1 PORT=8765 nohup node task-server.mjs > task-server.log 2>&1 &
```

验证：

```bash
curl http://127.0.0.1:8765/api/state
```

返回里 `tasks` 是空数组就清干净了，然后刷新看板页面。

注意：

- 如果只想删几条任务，直接在页面回收站点“彻底删除”即可，不需要动服务器文件。
- 页面上的“彻底删除”会写入 `task-archive.json`；要连归档一起清空时，按上面步骤操作。
- `rm -rf task-files/*` 会删除所有图片和文档附件，确认没有正式附件再执行。
- 清完不要保留旧的备份文件，否则以后排查时容易误用测试数据。

## 安全提醒

- 这是内部协作工具，没有细粒度账号和权限；一组共享密码即可。
- 公网部署请务必设置 `AUTH_PASS` 并使用 HTTPS（Nginx + certbot）。
- 附件以“强制下载”方式提供，避免上传的 SVG/HTML 在站点内被当作页面执行。
- 服务端单进程运行，不要用多个进程同时写同一个 `DATA_DIR`。
- 单个附件上限 100MB，单次请求体上限 200MB；Nginx 示例已配置 `client_max_body_size 200m`。

## 常见问题与排查

### 页面显示 `502 Bad Gateway`（Cloudflare / Nginx 报错）

这通常意味着 **Cloudflare 成功转发了请求，但源站的 Node 进程无法响应**。请按以下步骤排查：

**第一步：检查 Node 服务是否存活**

```bash
pm2 status                # 如果 state 是 stopped / errored，执行 pm2 restart task-board
ss -tlnp | grep 8765      # 确认端口被正常监听
```

**第二步：检查日志**

运行 `pm2 logs task-board` 或查看 Nginx 错误日志 `/var/log/nginx/error.log`。

**常见原因：**

- Node 进程因未捕获异常/内存泄漏崩溃（PM2 会自动拉起，但需要看日志修复 bug）。
- Nginx 反向代理超时（大附件上传/下载时需调整 `proxy_read_timeout`）。
- 端口被多个进程占用（用 `pkill -f task-server.mjs` 清理旧进程后再 `pm2 restart`）。

### 服务运行一段时间后自动退出

- 如果使用 PM2，检查 `pm2 status` 里的重启次数（`↺`）。如果不断增加，说明代码发生崩溃。通过 `pm2 logs task-board` 查看堆栈，定位未捕获的 `Exception` 或 `Promise Rejection`。
- 如果服务器内存不足，系统会因 OOM Killer 杀掉 Node 进程。检查系统日志：

```bash
dmesg -T | grep -i "killed process"
```

### 端口被占用

```bash
PORT=9000 node task-server.mjs
```

### 页面显示“数据初始化失败 / 无法连接服务器”

确认 `task-server.mjs` 正在运行，并且浏览器访问的地址和端口正确。看板页面必须通过该服务打开（`http://服务器IP:8765`），不要直接用 `file://` 双击打开。

### 忘记密码

修改 `.env` 文件或启动命令中的 `AUTH_PASS`，然后执行 `pm2 restart task-board --update-env` 或 `systemctl restart task-board`。

### 想清空所有任务

停服务后把 `task.json` 内容改成 `{"tasks": [], "groups": []}`，再启动即可。附件目录里不再被任何任务或归档引用的文件会在下次启动时自动清理。

注意：清空 `task.json` 不会清空 `task-archive.json`。归档是独立保留的，需要时可以单独备份或删除。
