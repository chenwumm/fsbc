# FSBC -- Forum System By Chenwu (晨雾论坛系统)
## 1.介绍
FSBC是一个终端论坛系统。用户可以通过nc或者telnet访问到论坛并使用论坛。
## 2.快速开始
克隆仓库:
```
git clone https://github.com/chenwumm/fsbc/
```
运行服务:
```
cd fsbc
python bbs.py &
```
停止服务:
```
pkill -f bbs.py
```
你可以用sed把源代码里面的论坛名称改成你自己的:
```
sed -i 's/FSBC论坛/你的论坛名/g' bbs.py
```
默认管理员用户:admin 密码:admin
可以通过cpolar等内网穿透服务暴露到公网。
欢迎提交Issues和PR！