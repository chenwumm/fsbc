# FSBC ─ Forum System By Chenwu（晨雾终端论坛）


FSBC 是一个**纯终端 BBS**。  
无需浏览器，打开任意支持 Telnet / Netcat 的终端即可访问：

```bash
telnet 你的服务器 2323
# 或
nc 你的服务器 2323
```

---

✨ 主要特性

- 多编码支持 – GBK / Big5 / UTF-8 自动协商  
- 用户系统 – 注册、登录、改名、改密、头像签名、兴趣标签  
- 个人主页 – 发帖/回复统计、最后活跃、在线状态  
- 在线列表 – 实时显示谁在线、登录时长、IP（10 min 无活动自动下线）  
- 内容管理 – 发帖、回复、置顶、删帖、分页浏览  
- 私信 & 举报 – 站内一键私信，违规用户随时举报  
- 权限分级 – 普通用户 / 版主 / 管理员，后端实时校验  
- 管理员后台 – 审核注册、封禁/解封、注销用户、板块增删、活跃排行  

---

🚀 快速开始

1. 克隆并启动  

```bash
git clone https://github.com/chenwumm/fsbc.git
cd fsbc
python bbs2.py &          # 默认监听 0.0.0.0:2323
```

2. 停止服务  

```bash
pkill -f bbs2.py
```

3. 自定义论坛名称（可选）  

```bash
sed -i 's/FSBC论坛/你的论坛名/g' bbs2.py
```

4. 暴露到公网（可选）

使用 cpolar、frp、云主机等将 2323 端口映射出去即可。

---

🔑 默认账户

用户名	密码	角色	
admin	admin	管理员	

首次登录后请尽快修改密码。

---

🛠 环境需求

- Python ≥ 3.6  
- 单文件部署，无额外依赖（仅使用标准库 + bcrypt）

---

📣 参与贡献

欢迎提 [Issue](https://github.com/chenwumm/fsbc/issues) 或 [Pull Request](https://github.com/chenwumm/fsbc/pulls) 一起完善功能！

---

晨雾 2026.1.23
Kimi AI帮助编写README