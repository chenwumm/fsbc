#!/data/data/com.termux/files/usr/bin/env python3
import socket, threading, json, os, datetime, bcrypt

DB_DIR   = os.path.dirname(os.path.abspath(__file__))
USERS_F  = os.path.join(DB_DIR, 'users.json')
BOARDS_F = os.path.join(DB_DIR, 'boards.json')

# ---------- 初始化 ----------
DEFAULT_BOARDS = {
    'Announce': {'desc': '站务公告', 'topics': []},
    'General':  {'desc': '综合讨论', 'topics': []},
    'Tech':     {'desc': '技术分享', 'topics': []}
}

if not os.path.exists(USERS_F):
    pwd_hash = bcrypt.hashpw(b'admin', bcrypt.gensalt()).decode()
    json.dump({'admin': {'pwd': pwd_hash, 'role': 'admin'}}, open(USERS_F, 'w'), indent=2)

if not os.path.exists(BOARDS_F):
    json.dump(DEFAULT_BOARDS, open(BOARDS_F, 'w'), indent=2)

USERS  = json.load(open(USERS_F))
BOARDS = json.load(open(BOARDS_F))

save_users  = lambda: json.dump(USERS,  open(USERS_F,  'w'), indent=2)
save_boards = lambda: json.dump(BOARDS, open(BOARDS_F, 'w'), indent=2)

def now(): return datetime.datetime.now().strftime('%m-%d %H:%M')

# ---------- 读写 ----------
def send(conn, s): conn.sendall((s + '\r\n').encode('utf-8'))

def recvline(conn, prompt=''):
    if prompt:
        send(conn, prompt)
    buf = b''
    while not buf.endswith(b'\n'):
        buf += conn.recv(1)
    return buf.decode('utf-8', 'ignore').strip('\r\n ')

def recv_multiline(conn, prompt='正文（最后一行单独输入 [EOF] 结束）：'):
    send(conn, prompt)
    lines = []
    while True:
        line = recvline(conn)
        if line == '[EOF]': break
        lines.append(line)
    return '\n'.join(lines)

# ---------- 权限 ----------
def role(user): return USERS[user]['role']
def is_admin(user): return role(user) == 'admin'
def is_mod(user):   return role(user) in ('admin', 'moderator')

# ---------- 板块 ----------
def list_boards(conn):
    send(conn, '\n=== FSBC论坛 ===')
    for idx,(name,meta) in enumerate(BOARDS.items(),1):
        send(conn, f'{idx}. {name} — {meta["desc"]}')
    send(conn, '0. 返回主菜单')

def add_board(conn, user):
    if not is_admin(user):
        send(conn, '无权限'); return
    name = recvline(conn, '新板块名称：').strip()
    if not name or name in BOARDS:
        send(conn, '名称无效或已存在'); return
    desc = recvline(conn, '板块描述：').strip()
    BOARDS[name] = {'desc': desc, 'topics': []}
    save_boards()
    send(conn, f'已新增板块「{name}」')

# 新增：删除板块功能
def delete_board(conn, user):
    if not is_admin(user):
        send(conn, '无权限'); return
    list_boards(conn)
    idx = recvline(conn, '请输入要删除的板块序号：')
    try:
        idx = int(idx) - 1
        board_name = list(BOARDS.keys())[idx]
        if board_name in ['Announce', 'General', 'Tech']:
            send(conn, '默认板块不可删除'); return
        del BOARDS[board_name]
        save_boards()
        send(conn, f'板块「{board_name}」已删除')
    except:
        send(conn, '无效操作')

# ---------- 帖子 ----------
def list_topics(conn, board):
    topics = BOARDS[board]['topics']
    send(conn, f'\n=== {board} ===')
    if not topics:
        send(conn, '暂无主题')
    else:
        for idx,t in enumerate(topics,1):
            send(conn, f'{idx}. {t["title"]} - {t["author"]} ({len(t["replies"])} 回复)')
    send(conn, 'n. 发表新主题  q. 返回')

def show_thread(conn, board, tid, user):
    t = BOARDS[board]['topics'][tid]
    send(conn, f'\n主题：{t["title"]}')
    send(conn, f'作者：{t["author"]}  时间：{t["time"]}')
    send(conn, '='*40)
    send(conn, t['content'])
    send(conn, '='*40)
    for r in t['replies']:
        send(conn, f'{r["author"]} {r["time"]}:\n{r["content"]}\n'+'-'*30)
    send(conn, 'r. 回复  d. 删除(仅管理员)  q. 返回')

# ---------- 用户管理 ----------
# 新增：修改用户名
def change_username(conn, current_user):
    new_name = recvline(conn, '请输入新用户名：').strip()
    if not new_name or new_name in USERS:
        send(conn, '用户名无效或已存在'); return
    # 迁移用户数据
    USERS[new_name] = USERS[current_user]
    del USERS[current_user]
    # 更新帖子和回复的作者信息
    for board in BOARDS.values():
        for topic in board['topics']:
            if topic['author'] == current_user:
                topic['author'] = new_name
            for reply in topic['replies']:
                if reply['author'] == current_user:
                    reply['author'] = new_name
    save_users()
    save_boards()
    send(conn, f'用户名已改为「{new_name}」，请重新登录')
    return new_name

# 新增：修改密码
def change_password(conn, user):
    old_pwd = recvline(conn, '请输入原密码：')
    if not bcrypt.checkpw(old_pwd.encode(), USERS[user]['pwd'].encode()):
        send(conn, '原密码错误'); return
    new_pwd = recvline(conn, '请输入新密码：')
    USERS[user]['pwd'] = bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt()).decode()
    save_users()
    send(conn, '密码修改成功')

# 新增：用户管理菜单
def user_management_menu(conn, user):
    while True:
        send(conn, '\n=== 用户管理 ===')
        send(conn, '1. 注销用户（仅管理员）')
        send(conn, '2. 修改当前用户名')
        send(conn, '3. 修改当前密码')
        send(conn, '0. 返回主菜单')
        cmd = recvline(conn)
        if cmd == '0':
            break
        elif cmd == '1':
            if not is_admin(user):
                send(conn, '无权限'); continue
            target = recvline(conn, '要注销的用户名：')
            if target == user:
                send(conn, '不可注销当前登录用户'); continue
            if target not in USERS:
                send(conn, '用户不存在'); continue
            del USERS[target]
            save_users()
            send(conn, f'用户「{target}」已注销')
        elif cmd == '2':
            new_user = change_username(conn, user)
            if new_user:
                return new_user  # 返回新用户名
        elif cmd == '3':
            change_password(conn, user)
    return user  # 未修改则返回原用户名

# ---------- 主循环 ----------
def handle_client(conn, addr):
    user = None
    # 登录/注册
    while not user:
        send(conn, '=== FSBC论坛 ===\n1. 登录  2. 注册  3. 退出')
        cmd = recvline(conn)
        if cmd == '3':
            conn.close(); return
        if cmd == '2':
            u = recvline(conn, '用户名：')
            if u in USERS:
                send(conn, '用户已存在'); continue
            pwd = recvline(conn, '密码：')
            USERS[u] = {'pwd': bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(), 'role': 'normal'}
            save_users(); send(conn, '注册成功')
        if cmd == '1':
            u = recvline(conn, '用户名：')
            pwd = recvline(conn, '密码：')
            if u not in USERS or not bcrypt.checkpw(pwd.encode(), USERS[u]['pwd'].encode()):
                send(conn, '用户名或密码错误'); continue
            user = u; send(conn, f'欢迎 {user}！')
    # 主菜单
    while True:
        send(conn, '\n主菜单：1 论坛  2 新增板块  3 删除板块  4 用户管理  5 退出')
        cmd = recvline(conn)
        if cmd == '5': break
        elif cmd == '3':
            delete_board(conn, user); continue
        elif cmd == '4':
            user = user_management_menu(conn, user); continue  # 处理用户名变更
        elif cmd == '2':
            add_board(conn, user); continue
        elif cmd == '1':
            while True:
                list_boards(conn)
                bch = recvline(conn)
                if bch == '0': break
                try:
                    board = list(BOARDS.keys())[int(bch)-1]
                except: send(conn, '无效选择'); continue
                while True:
                    list_topics(conn, board)
                    tch = recvline(conn)
                    if tch.lower() == 'q': break
                    if tch.lower() == 'n':
                        title   = recvline(conn, '标题：')
                        content = recv_multiline(conn)
                        BOARDS[board]['topics'].append({
                            'title': title, 'author': user, 'time': now(),
                            'content': content, 'replies': []
                        })
                        save_boards(); continue
                    try:
                        tid = int(tch)-1
                        topic = BOARDS[board]['topics'][tid]
                    except: continue
                    while True:
                        show_thread(conn, board, tid, user)
                        tcmd = recvline(conn)
                        if tcmd.lower() == 'q': break
                        if tcmd.lower() == 'r':
                            rpl = recv_multiline(conn, '回复内容：')
                            topic['replies'].append({'author': user, 'time': now(), 'content': rpl})
                            save_boards()
                        if tcmd.lower() == 'd' and is_admin(user):
                            del BOARDS[board]['topics'][tid]
                            save_boards(); send(conn, '已删除'); break
    conn.close()

# ---------- 启动 ----------
def main():
    HOST, PORT = '0.0.0.0', 2323
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT)); s.listen(10)
        print(f"FSBC论坛已启动 → telnet {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == '__main__':
    main()
