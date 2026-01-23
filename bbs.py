#!/data/data/com.termux/files/usr/bin/env python3
# -*- coding: utf-8 -*-
import socket, threading, json, os, datetime, bcrypt, time

# 基础配置
SUPPORT_ENCODINGS = {'1': 'gbk', '2': 'big5', '3': 'utf-8'}
ENCODE_PROMPT = """1) GBK  2) Big5  3) UTF-8
Please enter your encoding: """
PAGE_SIZE = 10
DB_DIR = os.path.dirname(os.path.abspath(__file__))

USERS_F   = os.path.join(DB_DIR, 'users.json')
BOARDS_F  = os.path.join(DB_DIR, 'boards.json')
MSGS_F    = os.path.join(DB_DIR, 'msgs.json')
REPORTS_F = os.path.join(DB_DIR, 'reports.json')
BANNED_F  = os.path.join(DB_DIR, 'banned.json')
PROFILES_F = os.path.join(DB_DIR, 'profiles.json')  # 新增：用户资料文件

# 在线用户管理
ONLINE_USERS = {}  # {用户名: {'conn': conn对象, 'addr': 地址, 'login_time': 登录时间, 'last_active': 最后活动时间}}

# 初始化文件
DEFAULT_BOARDS = {
    'Announce': {'desc': '站务公告', 'topics': []},
    'General':  {'desc': '综合讨论', 'topics': []},
    'Tech':     {'desc': '技术分享', 'topics': []}
}

# 如果文件不存在则创建
for f, init in [(USERS_F, {'admin': {'pwd': bcrypt.hashpw(b'admin', bcrypt.gensalt()).decode(), 'role': 'admin'}}),
                (BOARDS_F, DEFAULT_BOARDS),
                (MSGS_F, []),
                (REPORTS_F, []),
                (BANNED_F, []),
                (PROFILES_F, {})]:  # 新增：用户资料初始化
    if not os.path.exists(f):
        json.dump(init, open(f, 'w', encoding='utf-8'), indent=2)

# 加载数据到内存
USERS   = json.load(open(USERS_F, encoding='utf-8'))
BOARDS  = json.load(open(BOARDS_F, encoding='utf-8'))
MSGS    = json.load(open(MSGS_F, encoding='utf-8'))
REPORTS = json.load(open(REPORTS_F, encoding='utf-8'))
BANNED  = set(json.load(open(BANNED_F, encoding='utf-8')))
PROFILES = json.load(open(PROFILES_F, encoding='utf-8'))  # 新增：加载用户资料

# 初始化默认资料
for username in USERS:
    if username not in PROFILES:
        PROFILES[username] = {
            'signature': '这个人很懒，什么都没有写',
            'join_date': datetime.datetime.now().strftime('%Y-%m-%d'),
            'post_count': 0,
            'reply_count': 0,
            'last_active': '',
            'gender': '未设置',
            'interests': [],
            'bio': ''
        }

# 保存函数
save_users   = lambda: json.dump(USERS,  open(USERS_F,   'w', encoding='utf-8'), indent=2, ensure_ascii=False)
save_boards  = lambda: json.dump(BOARDS, open(BOARDS_F,  'w', encoding='utf-8'), indent=2, ensure_ascii=False)
save_msgs    = lambda: json.dump(MSGS,   open(MSGS_F,    'w', encoding='utf-8'), indent=2, ensure_ascii=False)
save_reports = lambda: json.dump(REPORTS,open(REPORTS_F,'w', encoding='utf-8'), indent=2, ensure_ascii=False)
save_banned  = lambda: json.dump(list(BANNED), open(BANNED_F,'w', encoding='utf-8'), indent=2)
save_profiles = lambda: json.dump(PROFILES, open(PROFILES_F, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)  # 新增

def now(): return datetime.datetime.now().strftime('%m-%d %H:%M')
def now_full(): return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 编码处理函数
def send_enc(conn, s, encoding):
    try:
        conn.sendall((s + '\r\n').encode(encoding))
    except:
        conn.sendall((s + '\r\n').encode('utf-8'))

def recvline_enc(conn, encoding, prompt=''):
    if prompt:
        send_enc(conn, prompt, encoding)
    buf = b''
    while not buf.endswith(b'\n'):
        chunk = conn.recv(1)
        if not chunk:
            break
        buf += chunk
    try:
        return buf.decode(encoding).strip('\r\n ')
    except:
        return buf.decode('utf-8', errors='ignore').strip('\r\n ')

def recv_multiline_enc(conn, encoding, prompt='内容(最后一行单独输入.结束)：'):
    send_enc(conn, prompt, encoding)
    lines = []
    while True:
        line = recvline_enc(conn, encoding, '')
        if line == '.':
            break
        lines.append(line)
    return '\n'.join(lines)

# 分页工具
def get_paginated_data(data_list, page):
    total = len(data_list)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    return data_list[start:end], total_pages, page

# 权限检查函数
def role(user): return USERS[user]['role']
def is_admin(user): return role(user) == 'admin'
def is_mod(user): return role(user) in ('admin', 'moderator')
def is_normal(user): return role(user) == 'normal'
def is_pending(user): return role(user) == 'pending'
def is_banned(user): return user in BANNED

# 更新用户统计（发帖/回复时调用）
def update_post_count(user, post_type='reply'):
    if user not in PROFILES:
        return
    if post_type == 'topic':
        PROFILES[user]['post_count'] = PROFILES[user].get('post_count', 0) + 1
    elif post_type == 'reply':
        PROFILES[user]['reply_count'] = PROFILES[user].get('reply_count', 0) + 1
    PROFILES[user]['last_active'] = now_full()
    save_profiles()

# 在线用户管理
def add_online_user(username, conn, addr):
    ONLINE_USERS[username] = {
        'conn': conn,
        'addr': addr,
        'login_time': time.time(),
        'last_active': time.time()
    }

def remove_online_user(username):
    if username in ONLINE_USERS:
        del ONLINE_USERS[username]

def update_user_active(username):
    if username in ONLINE_USERS:
        ONLINE_USERS[username]['last_active'] = time.time()

def get_online_users():
    # 清理超时用户（10分钟无活动）
    timeout = 600  # 10分钟
    current_time = time.time()
    to_remove = []
    for user, info in ONLINE_USERS.items():
        if current_time - info['last_active'] > timeout:
            to_remove.append(user)
    for user in to_remove:
        del ONLINE_USERS[user]
    
    return ONLINE_USERS

# 显示在线用户列表
def show_online_users_enc(conn, user, encoding):
    online_users = get_online_users()
    total = len(online_users)
    
    send_enc(conn, '\n=== 在线用户列表 ===', encoding)
    send_enc(conn, f'当前在线：{total} 人', encoding)
    send_enc(conn, '=' * 40, encoding)
    
    if total == 0:
        send_enc(conn, '暂无在线用户', encoding)
        return
    
    # 分页显示
    user_list = list(online_users.items())
    current_page = 1
    while True:
        paginated, total_pages, current_page = get_paginated_data(user_list, current_page)
        
        send_enc(conn, f'【分页】第{current_page}/{total_pages}页', encoding)
        send_enc(conn, '-' * 40, encoding)
        
        for idx, (username, info) in enumerate(paginated, 1):
            real_idx = (current_page - 1) * PAGE_SIZE + idx
            duration = int(time.time() - info['login_time'])
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            
            # 获取用户角色
            user_role = role(username)
            role_prefix = {
                'admin': '[A]',
                'moderator': '[M]',
                'normal': '',
                'pending': '[P]'
            }.get(user_role, '')
            
            # 显示用户状态
            status = ""
            if username == user:
                status = "[我]"
            
            send_enc(conn, f'{real_idx}. {role_prefix}{username}{status}', encoding)
            send_enc(conn, f'   登录时间：{time.strftime("%H:%M:%S", time.localtime(info["login_time"]))}', encoding)
            send_enc(conn, f'   在线时长：{hours}小时{minutes}分钟', encoding)
            send_enc(conn, f'   IP地址：{info["addr"][0]}', encoding)
            send_enc(conn, '-' * 30, encoding)
        
        send_enc(conn, '\n操作：p上一页 n下一页 v查看用户资料  q返回', encoding)
        cmd = recvline_enc(conn, encoding, '请选择：').strip().lower()
        
        if cmd == 'q':
            break
        elif cmd == 'p' and current_page > 1:
            current_page -= 1
        elif cmd == 'n' and current_page < total_pages:
            current_page += 1
        elif cmd == 'v':
            target = recvline_enc(conn, encoding, '输入要查看的用户名（输入0返回）：').strip()
            if target == '0':
                continue
            if target in USERS:
                show_user_profile_enc(conn, target, encoding, user)
            else:
                send_enc(conn, '用户不存在', encoding)

# 显示用户个人资料
def show_user_profile_enc(conn, target_user, encoding, current_user=None):
    if target_user not in PROFILES:
        PROFILES[target_user] = {
            'signature': '这个人很懒，什么都没有写',
            'join_date': datetime.datetime.now().strftime('%Y-%m-%d'),
            'post_count': 0,
            'reply_count': 0,
            'last_active': '',
            'gender': '未设置',
            'interests': [],
            'bio': ''
        }
        save_profiles()
    
    profile = PROFILES[target_user]
    
    send_enc(conn, f'\n=== {target_user} 的个人资料 ===', encoding)
    send_enc(conn, '=' * 50, encoding)
    
    # 基础信息
    send_enc(conn, f'签名：{profile.get("signature", "未设置")}', encoding)
    send_enc(conn, f'角色：{role(target_user)}', encoding)
    send_enc(conn, f'注册时间：{profile.get("join_date", "未知")}', encoding)
    send_enc(conn, f'性别：{profile.get("gender", "未设置")}', encoding)
    
    # 统计信息
    send_enc(conn, f'发帖数：{profile.get("post_count", 0)}', encoding)
    send_enc(conn, f'回复数：{profile.get("reply_count", 0)}', encoding)
    send_enc(conn, f'总贡献：{profile.get("post_count", 0) + profile.get("reply_count", 0)}', encoding)
    
    # 最后活动时间
    last_active = profile.get('last_active', '从未活动')
    send_enc(conn, f'最后活动：{last_active}', encoding)
    
    # 在线状态
    if target_user in ONLINE_USERS:
        send_enc(conn, '当前状态：在线', encoding)
    else:
        send_enc(conn, '当前状态：离线', encoding)
    
    # 兴趣爱好
    interests = profile.get('interests', [])
    if interests:
        send_enc(conn, f'兴趣：{", ".join(interests)}', encoding)
    
    # 个人简介
    bio = profile.get('bio', '')
    if bio:
        send_enc(conn, f'\n个人简介：', encoding)
        # 分页显示简介
        bio_lines = bio.split('\n')
        for line in bio_lines:
            send_enc(conn, f'   {line}', encoding)
    
    send_enc(conn, '=' * 50, encoding)
    
    # 操作菜单
    if current_user == target_user:
        # 自己的资料可以编辑
        send_enc(conn, '操作：1.编辑资料 2.查看我的帖子 0.返回', encoding)
        cmd = recvline_enc(conn, encoding, '请选择：').strip()
        if cmd == '1':
            edit_profile_enc(conn, target_user, encoding)
        elif cmd == '2':
            show_user_posts_enc(conn, target_user, encoding)
        elif cmd == '0':
            return
    else:
        # 查看他人资料的操作
        send_enc(conn, '操作：1.发送私信 2.查看TA的帖子 3.举报用户 0.返回', encoding)
        cmd = recvline_enc(conn, encoding, '请选择：').strip()
        if cmd == '1':
            if is_banned(current_user):
                send_enc(conn, '你已被封禁，无法发私信！', encoding)
                return
            content = recv_multiline_enc(conn, encoding, '私信内容（单行.结束）：')
            MSGS.append({'sender': current_user, 'receiver': target_user, 
                        'content': content, 'time': now(), 'is_read': False})
            save_msgs()
            send_enc(conn, '私信已发送', encoding)
        elif cmd == '2':
            show_user_posts_enc(conn, target_user, encoding)
        elif cmd == '3':
            reason = recv_multiline_enc(conn, encoding, '举报理由（单行.结束）：')
            add_report(current_user, target_user, reason)
            send_enc(conn, '举报已提交', encoding)

# 编辑个人资料
def edit_profile_enc(conn, username, encoding):
    while True:
        profile = PROFILES[username]
        send_enc(conn, '\n=== 编辑个人资料 ===', encoding)
        send_enc(conn, f'1. 签名 [{profile.get("signature", "未设置")}]', encoding)
        send_enc(conn, f'2. 性别 [{profile.get("gender", "未设置")}]', encoding)
        send_enc(conn, f'3. 兴趣爱好 [{", ".join(profile.get("interests", []))}]', encoding)
        send_enc(conn, f'4. 个人简介', encoding)
        send_enc(conn, '0. 返回', encoding)
        
        cmd = recvline_enc(conn, encoding, '请选择：').strip()
        
        if cmd == '0':
            break
        elif cmd == '1':
            new_sig = recvline_enc(conn, encoding, '新签名（最多50字）：').strip()[:50]
            profile['signature'] = new_sig
            save_profiles()
            send_enc(conn, '签名已更新', encoding)
        elif cmd == '2':
            send_enc(conn, '选择性别：1.男 2.女 3.保密', encoding)
            choice = recvline_enc(conn, encoding, '').strip()
            gender_map = {'1': '男', '2': '女', '3': '保密'}
            if choice in gender_map:
                profile['gender'] = gender_map[choice]
                save_profiles()
                send_enc(conn, '性别已更新', encoding)
        elif cmd == '3':
            current = profile.get('interests', [])
            send_enc(conn, f'当前兴趣：{", ".join(current) if current else "无"}', encoding)
            send_enc(conn, '输入新兴趣（多个用逗号分隔，留空清空）：', encoding)
            new_interests = recvline_enc(conn, encoding, '').strip()
            if new_interests:
                interests_list = [i.strip() for i in new_interests.split(',') if i.strip()]
                profile['interests'] = interests_list[:10]  # 最多10个
            else:
                profile['interests'] = []
            save_profiles()
            send_enc(conn, '兴趣已更新', encoding)
        elif cmd == '4':
            send_enc(conn, f'当前简介：\n{profile.get("bio", "暂无")}', encoding)
            send_enc(conn, '输入新简介（单行.结束）：', encoding)
            new_bio = recv_multiline_enc(conn, encoding, '')
            profile['bio'] = new_bio[:500]  # 限制500字
            save_profiles()
            send_enc(conn, '个人简介已更新', encoding)

# 显示用户的帖子
def show_user_posts_enc(conn, username, encoding):
    send_enc(conn, f'\n=== {username} 的发帖记录 ===', encoding)
    
    all_posts = []
    # 收集用户的所有主帖
    for board_name, board_data in BOARDS.items():
        for topic in board_data['topics']:
            if topic['author'] == username:
                all_posts.append({
                    'board': board_name,
                    'title': topic['title'],
                    'time': topic['time'],
                    'content_preview': topic['content'][:50] + '...' if len(topic['content']) > 50 else topic['content']
                })
    
    if not all_posts:
        send_enc(conn, '该用户还没有发表过主题', encoding)
        recvline_enc(conn, encoding, '输入任意键返回：')
        return
    
    current_page = 1
    while True:
        paginated, total_pages, current_page = get_paginated_data(all_posts, current_page)
        
        send_enc(conn, f'【分页】第{current_page}/{total_pages}页 | 共{len(all_posts)}条主题', encoding)
        send_enc(conn, '-' * 60, encoding)
        
        for idx, post in enumerate(paginated, 1):
            real_idx = (current_page - 1) * PAGE_SIZE + idx
            send_enc(conn, f'{real_idx}. {post["title"]}', encoding)
            send_enc(conn, f'   板块：{post["board"]} | 时间：{post["time"]}', encoding)
            send_enc(conn, f'   预览：{post["content_preview"]}', encoding)
            send_enc(conn, '-' * 40, encoding)
        
        send_enc(conn, '\n操作：数字查看详情 p上一页 n下一页 q返回', encoding)
        cmd = recvline_enc(conn, encoding, '请选择：').strip().lower()
        
        if cmd == 'q':
            break
        elif cmd == 'p' and current_page > 1:
            current_page -= 1
        elif cmd == 'n' and current_page < total_pages:
            current_page += 1
        elif cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(all_posts):
                post = all_posts[idx]
                send_enc(conn, f'\n=== {post["title"]} ===', encoding)
                send_enc(conn, f'板块：{post["board"]} | 作者：{username} | 时间：{post["time"]}', encoding)
                send_enc(conn, '-' * 50, encoding)
                # 需要找到原帖内容
                for topic in BOARDS[post['board']]['topics']:
                    if topic['author'] == username and topic['title'] == post['title']:
                        send_enc(conn, topic['content'], encoding)
                        break
                send_enc(conn, '-' * 50, encoding)
                recvline_enc(conn, encoding, '输入任意键返回：')

# 举报功能
def add_report(reporter, target, reason):
    REPORTS.append({'reporter': reporter, 'target': target, 'reason': reason, 'time': now()})
    save_reports()

# 板块列表
def list_boards_enc(conn, encoding):
    send_enc(conn, '\n===FSBC论坛===', encoding)
    for idx, (name, meta) in enumerate(BOARDS.items(), 1):
        send_enc(conn, f'{idx}. {name} — {meta["desc"]}', encoding)
    send_enc(conn, '0. 返回主菜单', encoding)

# 帖子列表
def list_topics_enc(conn, board, encoding):
    topics = BOARDS[board]['topics']
    send_enc(conn, f'\n=== {board} 板块 ===', encoding)
    if not topics:
        send_enc(conn, '暂无主题', encoding)
        send_enc(conn, 's. 发表新主题  q. 返回', encoding)
        cmd = recvline_enc(conn, encoding, '请选择操作：').lower()
        return 'new' if cmd == 's' else 'q' if cmd == 'q' else cmd
    current_page = 1
    while True:
        paginated, total_pages, current_page = get_paginated_data(topics, current_page)
        send_enc(conn, f'【分页】第{current_page}/{total_pages}页 | 共{len(topics)}条', encoding)
        for idx, t in enumerate(paginated, 1):
            real_idx = (current_page - 1) * PAGE_SIZE + idx
            send_enc(conn, f'{real_idx}. {t["title"]} - {t["author"]} ({len(t["replies"])} 回复)', encoding)
        send_enc(conn, '\n操作：数字看帖 s发帖 q返回 #跳页 p上 n下', encoding)
        cmd = recvline_enc(conn, encoding, '请选择：').strip().lower()
        if cmd.isdigit():
            tid = int(cmd)
            if 1 <= tid <= len(topics):
                return str(tid)
        elif cmd == 's':
            return 'new'
        elif cmd == 'q':
            return 'q'
        elif cmd == 'p' and current_page > 1:
            current_page -= 1
        elif cmd == 'n' and current_page < total_pages:
            current_page += 1
        elif cmd.startswith('#') and cmd[1:].isdigit():
            pg = int(cmd[1:])
            if 1 <= pg <= total_pages:
                current_page = pg

# 帖子详情
def show_thread_enc(conn, board, tid, user, encoding):
    t = BOARDS[board]['topics'][tid]
    send_enc(conn, f'\n=== 主题：{t["title"]} ===', encoding)
    send_enc(conn, f'作者：{t["author"]}  时间：{t["time"]}', encoding)
    send_enc(conn, '=' * 40, encoding)
    send_enc(conn, t['content'], encoding)
    send_enc(conn, '=' * 40, encoding)
    replies = t['replies']
    send_enc(conn, f'【回复区】共{len(replies)}条', encoding)

    current_page = 1
    while True:
        paginated, total_pages, current_page = get_paginated_data(replies, current_page)
        send_enc(conn, f'\n回复【第{current_page}/{total_pages}页】', encoding)
        for idx, r in enumerate(paginated, 1):
            real_idx = (current_page - 1) * PAGE_SIZE + idx
            send_enc(conn, f'{real_idx}. {r["author"]} ({r["time"]})：\n{r["content"]}', encoding)
            send_enc(conn, '-' * 30, encoding)
        base = 'r回复  d删帖  dr删回复  q返回列表'
        mod_extra = '  t置顶帖  c取消置顶  tr置顶回复  ctr取消回复置顶'
        extra = '  ru举报用户  v查看作者资料'
        send_enc(conn, '\n操作：' + base + (mod_extra if is_mod(user) else '') + extra, encoding)
        cmd = recvline_enc(conn, encoding, '请选择：').lower()
        update_user_active(user)  # 更新活动时间
        
        if cmd == 'q':
            return 'q'
        elif cmd == 'r':
            if is_banned(user):
                send_enc(conn, '你已被封禁，无法回复！', encoding)
                continue
            rpl = recv_multiline_enc(conn, encoding, '回复内容（单行.结束）：')
            replies.append({'author': user, 'time': now(), 'content': rpl})
            save_boards()
            update_post_count(user, 'reply')  # 更新回复计数
            send_enc(conn, '回复成功！', encoding)
        elif cmd == 'd':
            if is_mod(user) or t['author'] == user:
                sure = recvline_enc(conn, encoding, '确认删除整个帖子？(y/n)：').lower()
                if sure == 'y':
                    del BOARDS[board]['topics'][tid]
                    save_boards()
                    send_enc(conn, '帖子已删除', encoding)
                    return 'q'
            else:
                send_enc(conn, '无权限删帖', encoding)
        elif cmd == 'dr':
            if not replies:
                send_enc(conn, '暂无回复', encoding)
                continue
            try:
                ridx = int(recvline_enc(conn, encoding, '要删除的回复序号：')) - 1
                if 0 <= ridx < len(replies):
                    if is_mod(user) or replies[ridx]['author'] == user:
                        del replies[ridx]
                        save_boards()
                        send_enc(conn, '回复已删', encoding)
                    else:
                        send_enc(conn, '无权限', encoding)
            except:
                send_enc(conn, '序号无效', encoding)
        elif cmd in ['t', 'c'] and is_mod(user):
            if cmd == 't':
                t['title'] = '[置顶]' + t['title'].replace('[置顶]', '')
                BOARDS[board]['topics'].insert(0, BOARDS[board]['topics'].pop(tid))
                save_boards()
                send_enc(conn, '帖子已置顶', encoding)
                return 'q'
            else:
                t['title'] = t['title'].replace('[置顶]', '')
                save_boards()
                send_enc(conn, '已取消置顶', encoding)
        elif cmd == 'ru':
            target = recvline_enc(conn, encoding, '举报用户名：').strip()
            if target not in USERS:
                send_enc(conn, '用户不存在', encoding)
                continue
            if target == user:
                send_enc(conn, '不能举报自己', encoding)
                continue
            reason = recv_multiline_enc(conn, encoding, '举报理由（单行.结束）：')
            add_report(user, target, reason)
            send_enc(conn, '举报已提交，管理员会处理！', encoding)
        elif cmd == 'v':
            show_user_profile_enc(conn, t['author'], encoding, user)

# 用户管理（含管理员功能）
def user_management_menu_enc(conn, user, encoding):
    while True:
        send_enc(conn, '\n=== 用户管理 ===', encoding)
        send_enc(conn, '1. 查看/编辑个人资料', encoding)
        send_enc(conn, '2. 修改自己的用户名', encoding)
        send_enc(conn, '3. 修改自己的密码', encoding)
        send_enc(conn, '4. 查看在线用户', encoding)
        send_enc(conn, '5. 举报用户（ru）', encoding)
        if is_admin(user):
            send_enc(conn, '6. 查看举报列表', encoding)
            send_enc(conn, '7. 封禁用户', encoding)
            send_enc(conn, '8. 解封用户', encoding)
            send_enc(conn, '9. 审核注册申请', encoding)
            send_enc(conn, '10. 设置/取消版主', encoding)
            send_enc(conn, '11. 注销用户', encoding)
            send_enc(conn, '12. 查看用户统计', encoding)
        send_enc(conn, '0. 返回主菜单', encoding)
        cmd = recvline_enc(conn, encoding, '请选择：').strip()
        update_user_active(user)  # 更新活动时间
        
        if cmd == '0':
            break
        elif cmd == '1':
            show_user_profile_enc(conn, user, encoding, user)
        elif cmd == '2':
            # 修改用户名
            new = recvline_enc(conn, encoding, '新用户名：').strip()
            if not new or new in USERS:
                send_enc(conn, '用户名无效或已存在', encoding)
                continue
            # 同步更新所有数据
            for b in BOARDS.values():
                for t in b['topics']:
                    if t['author'] == user:
                        t['author'] = new
                    for r in t['replies']:
                        if r['author'] == user:
                            r['author'] = new
            for m in MSGS:
                if m['sender'] == user:
                    m['sender'] = new
                if m['receiver'] == user:
                    m['receiver'] = new
            # 更新用户资料
            if user in PROFILES:
                PROFILES[new] = PROFILES.pop(user)
            
            USERS[new] = USERS.pop(user)
            save_users()
            save_boards()
            save_msgs()
            save_profiles()
            
            # 更新在线用户列表
            if user in ONLINE_USERS:
                ONLINE_USERS[new] = ONLINE_USERS.pop(user)
            
            send_enc(conn, f'用户名已改为 {new}，请重新登录', encoding)
            return new
        elif cmd == '3':
            # 修改密码
            old = recvline_enc(conn, encoding, '原密码：')
            if not bcrypt.checkpw(old.encode(), USERS[user]['pwd'].encode()):
                send_enc(conn, '原密码错误', encoding)
                continue
            new = recvline_enc(conn, encoding, '新密码：')
            USERS[user]['pwd'] = bcrypt.hashpw(new.encode(), bcrypt.gensalt()).decode()
            save_users()
            send_enc(conn, '密码已修改', encoding)
        elif cmd == '4':
            show_online_users_enc(conn, user, encoding)
        elif cmd == '5':
            # 举报用户
            target = recvline_enc(conn, encoding, '举报用户名：').strip()
            if target not in USERS:
                send_enc(conn, '用户不存在', encoding)
                continue
            if target == user:
                send_enc(conn, '不能举报自己', encoding)
                continue
            reason = recv_multiline_enc(conn, encoding, '举报理由（单行.结束）：')
            add_report(user, target, reason)
            send_enc(conn, '举报已提交，管理员会处理！', encoding)
        elif cmd == '6' and is_admin(user):
            # 查看举报列表
            if not REPORTS:
                send_enc(conn, '暂无举报', encoding)
                continue
            for idx, r in enumerate(REPORTS, 1):
                send_enc(conn, f'{idx}. {r["reporter"]} 举报 {r["target"]} ({r["time"]})', encoding)
                send_enc(conn, f'   理由：{r["reason"]}', encoding)
            recvline_enc(conn, encoding, '输入任意键返回：')
        elif cmd == '7' and is_admin(user):
            # 封禁
            target = recvline_enc(conn, encoding, '要封禁的用户名：').strip()
            if target not in USERS:
                send_enc(conn, '用户不存在', encoding)
                continue
            if target == user:
                send_enc(conn, '不能封禁自己', encoding)
                continue
            if target in BANNED:
                send_enc(conn, '该用户已被封禁', encoding)
                continue
            sure = recvline_enc(conn, encoding, f'确认封禁 {target} ？(y/n)：').lower()
            if sure == 'y':
                BANNED.add(target)
                save_banned()
                # 从在线用户中移除
                if target in ONLINE_USERS:
                    remove_online_user(target)
                send_enc(conn, f'{target} 已被封禁，无法发帖/私信', encoding)
        elif cmd == '8' and is_admin(user):
            # 解封
            if not BANNED:
                send_enc(conn, '暂无被封用户', encoding)
                continue
            send_enc(conn, '被封用户：' + ', '.join(BANNED), encoding)
            target = recvline_enc(conn, encoding, '要解封的用户名：').strip()
            if target not in BANNED:
                send_enc(conn, '该用户未被封禁', encoding)
                continue
            sure = recvline_enc(conn, encoding, f'确认解封 {target} ？(y/n)：').lower()
            if sure == 'y':
                BANNED.discard(target)
                save_banned()
                send_enc(conn, f'{target} 已解封', encoding)
        elif cmd == '9' and is_admin(user):
            # 审核注册
            pending = [u for u in USERS if is_pending(u)]
            if not pending:
                send_enc(conn, '暂无待审核用户', encoding)
                continue
            for idx, u in enumerate(pending, 1):
                send_enc(conn, f'{idx}. {u}', encoding)
            try:
                i = int(recvline_enc(conn, encoding, '输入序号（0返回）：')) - 1
                if i == -1:
                    continue
                u = pending[i]
            except:
                send_enc(conn, '序号无效', encoding)
                continue
            send_enc(conn, f'审核 {u} ：1通过  2拒绝', encoding)
            c = recvline_enc(conn, encoding, '').strip()
            if c == '1':
                USERS[u]['role'] = 'normal'
                save_users()
                send_enc(conn, '审核通过', encoding)
            elif c == '2':
                del USERS[u]
                save_users()
                send_enc(conn, '已拒绝并删除', encoding)
        elif cmd == '10' and is_admin(user):
            # 设置/取消版主
            target = recvline_enc(conn, encoding, '用户名：').strip()
            if target not in USERS:
                send_enc(conn, '用户不存在', encoding)
                continue
            if role(target) == 'moderator':
                sure = recvline_enc(conn, encoding, f'取消 {target} 版主身份？(y/n)：').lower()
                if sure == 'y':
                    USERS[target]['role'] = 'normal'
                    save_users()
                    send_enc(conn, '已取消版主', encoding)
            else:
                sure = recvline_enc(conn, encoding, f'设 {target} 为版主？(y/n)：').lower()
                if sure == 'y':
                    USERS[target]['role'] = 'moderator'
                    save_users()
                    send_enc(conn, '已设为版主', encoding)
        elif cmd == '11' and is_admin(user):
            # 注销用户
            target = recvline_enc(conn, encoding, '要注销的用户名：').strip()
            if target not in USERS:
                send_enc(conn, '用户不存在', encoding)
                continue
            if target == user:
                send_enc(conn, '不能注销自己', encoding)
                continue
            sure = recvline_enc(conn, encoding, f'确认注销 {target} ？(y/n)：').lower()
            if sure == 'y':
                del USERS[target]
                # 从在线用户中移除
                if target in ONLINE_USERS:
                    remove_online_user(target)
                # 清理用户资料
                if target in PROFILES:
                    del PROFILES[target]
                save_users()
                save_profiles()
                send_enc(conn, '用户已注销', encoding)
        elif cmd == '12' and is_admin(user):
            # 查看用户统计
            send_enc(conn, '\n=== 用户统计 ===', encoding)
            send_enc(conn, f'总用户数：{len(USERS)}', encoding)
            send_enc(conn, f'在线用户：{len(ONLINE_USERS)}', encoding)
            send_enc(conn, f'待审核用户：{len([u for u in USERS if is_pending(u)])}', encoding)
            send_enc(conn, f'被封禁用户：{len(BANNED)}', encoding)
            send_enc(conn, '-' * 40, encoding)
            # 活跃用户排行
            active_users = []
            for username, profile in PROFILES.items():
                if username in USERS and not is_pending(username):
                    total_posts = profile.get('post_count', 0) + profile.get('reply_count', 0)
                    active_users.append((username, total_posts))
            
            active_users.sort(key=lambda x: x[1], reverse=True)
            send_enc(conn, '【活跃用户排行榜】', encoding)
            for idx, (username, count) in enumerate(active_users[:10], 1):
                send_enc(conn, f'{idx}. {username}: {count} 条', encoding)
            recvline_enc(conn, encoding, '输入任意键返回：')
    return user

# 主客户端处理函数
def handle_client(conn, addr):
    # 选择编码
    encoding = 'utf-8'
    while True:
        try:
            conn.sendall(ENCODE_PROMPT.encode('utf-8'))
            enc_choice = conn.recv(10).decode('utf-8').strip()
            if enc_choice in SUPPORT_ENCODINGS:
                encoding = SUPPORT_ENCODINGS[enc_choice]
                break
            else:
                conn.sendall('无效选择，默认UTF-8\n'.encode('utf-8'))
                break
        except:
            conn.sendall('编码选择失败，默认UTF-8\n'.encode('utf-8'))
            break

    # 登录/注册流程
    user = None
    while not user:
        send_enc(conn, '\n===FSBC论坛===', encoding)
        send_enc(conn, '1. 登录  2. 注册  3. 退出', encoding)
        cmd = recvline_enc(conn, encoding, '').strip()
        if cmd == '3':
            conn.close()
            return
        if cmd == '2':
            u = recvline_enc(conn, encoding, '注册用户名：').strip()
            if u in USERS:
                send_enc(conn, '用户名已存在', encoding)
                continue
            pwd = recvline_enc(conn, encoding, '密码：')
            USERS[u] = {'pwd': bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode(), 'role': 'pending'}
            # 初始化用户资料
            PROFILES[u] = {
                'signature': '这个人很懒，什么都没有写',
                'join_date': datetime.datetime.now().strftime('%Y-%m-%d'),
                'post_count': 0,
                'reply_count': 0,
                'last_active': '',
                'gender': '未设置',
                'interests': [],
                'bio': ''
            }
            save_users()
            save_profiles()
            send_enc(conn, '注册成功，请等待审核', encoding)
        if cmd == '1':
            u = recvline_enc(conn, encoding, '用户名：').strip()
            pwd = recvline_enc(conn, encoding, '密码：')
            if u not in USERS or not bcrypt.checkpw(pwd.encode(), USERS[u]['pwd'].encode()):
                send_enc(conn, '用户名或密码错误', encoding)
                continue
            if is_pending(u):
                send_enc(conn, '账号审核中，请稍后再试', encoding)
                continue
            if is_banned(u):
                send_enc(conn, '你已被封禁，仅可浏览', encoding)
            user = u
            # 添加到在线用户列表
            add_online_user(user, conn, addr)
            # 更新最后活动时间
            if user in PROFILES:
                PROFILES[user]['last_active'] = now_full()
                save_profiles()
            send_enc(conn, f'欢迎 {user}！身份：{role(user)}', encoding)
            send_enc(conn, f'当前在线用户：{len(ONLINE_USERS)} 人', encoding)

    # 主菜单循环
    while True:
        send_enc(conn, f'\n主菜单：1 论坛  2 板块管理  3 用户管理  4 私信  5 在线用户({len(ONLINE_USERS)})  6 退出', encoding)
        cmd = recvline_enc(conn, encoding, '').strip()
        update_user_active(user)  # 更新活动时间
        
        if cmd == '6':
            break
        elif cmd == '3':
            new_user = user_management_menu_enc(conn, user, encoding)
            if new_user:
                user = new_user
                continue
        elif cmd == '5':
            # 查看在线用户
            show_online_users_enc(conn, user, encoding)
        elif cmd == '4':
            # 私信菜单
            while True:
                send_enc(conn, '\n私信：1发信  2收信  0返回', encoding)
                c = recvline_enc(conn, encoding, '').strip()
                update_user_active(user)
                if c == '0':
                    break
                if c == '1':
                    if is_banned(user):
                        send_enc(conn, '你已被封禁，无法发私信！', encoding)
                        continue
                    to = recvline_enc(conn, encoding, '发给：').strip()
                    if to not in USERS:
                        send_enc(conn, '用户不存在', encoding)
                        continue
                    if to == user:
                        send_enc(conn, '不能发给自己', encoding)
                        continue
                    content = recv_multiline_enc(conn, encoding, '内容（单行.结束）：')
                    MSGS.append({'sender': user, 'receiver': to, 'content': content, 'time': now(), 'is_read': False})
                    save_msgs()
                    send_enc(conn, '私信已发送', encoding)
                if c == '2':
                    mine = [m for m in MSGS if m['receiver'] == user]
                    if not mine:
                        send_enc(conn, '暂无私信', encoding)
                        continue
                    mine.reverse()
                    for idx, m in enumerate(mine, 1):
                        mark = '【未读】' if not m['is_read'] else ''
                        send_enc(conn, f'{idx}. {mark}{m["sender"]} {m["time"]}', encoding)
                        send_enc(conn, f'    {m["content"][:30]}...', encoding)
                    recvline_enc(conn, encoding, '输入任意键返回：')
        elif cmd == '2':
            # 板块管理（仅管理员）
            if not is_admin(user):
                send_enc(conn, '无权限', encoding)
                continue
            while True:
                send_enc(conn, '\n板块管理：1新增  2删除  0返回', encoding)
                c = recvline_enc(conn, encoding, '').strip()
                update_user_active(user)
                if c == '0':
                    break
                if c == '1':
                    name = recvline_enc(conn, encoding, '新板块名称：').strip()
                    if not name or name in BOARDS:
                        send_enc(conn, '名称无效或已存在', encoding)
                        continue
                    desc = recvline_enc(conn, encoding, '板块描述：').strip()
                    BOARDS[name] = {'desc': desc, 'topics': []}
                    save_boards()
                    send_enc(conn, '板块已添加', encoding)
                if c == '2':
                    list_boards_enc(conn, encoding)
                    try:
                        i = int(recvline_enc(conn, encoding, '要删除的序号：')) - 1
                        name = list(BOARDS.keys())[i]
                    except:
                        send_enc(conn, '序号无效', encoding)
                        continue
                    if name in DEFAULT_BOARDS:
                        send_enc(conn, '默认板块不可删', encoding)
                        continue
                    sure = recvline_enc(conn, encoding, f'确认删除 {name} ？(y/n)：').lower()
                    if sure == 'y':
                        del BOARDS[name]
                        save_boards()
                        send_enc(conn, '板块已删除', encoding)
        elif cmd == '1':
            # 论坛浏览
            while True:
                list_boards_enc(conn, encoding)
                bch = recvline_enc(conn, encoding, '选择板块序号（0返回）：').strip()
                update_user_active(user)
                if bch == '0':
                    break
                try:
                    board = list(BOARDS.keys())[int(bch) - 1]
                except:
                    send_enc(conn, '无效选择', encoding)
                    continue
                while True:
                    topic_cmd = list_topics_enc(conn, board, encoding)
                    update_user_active(user)
                    if topic_cmd == 'new':
                        if is_banned(user):
                            send_enc(conn, '你已被封禁，无法发帖！', encoding)
                            continue
                        title = recvline_enc(conn, encoding, '标题：').strip()
                        content = recv_multiline_enc(conn, encoding, '正文（单行.结束）：')
                        BOARDS[board]['topics'].append({
                            'title': title, 'author': user, 'time': now(),
                            'content': content, 'replies': []
                        })
                        save_boards()
                        update_post_count(user, 'topic')  # 更新发帖计数
                        send_enc(conn, '发帖成功！', encoding)
                    elif topic_cmd == 'q':
                        break
                    else:
                        try:
                            tid = int(topic_cmd) - 1
                            t = BOARDS[board]['topics'][tid]
                        except:
                            continue
                        show_thread_enc(conn, board, tid, user, encoding)
        else:
            send_enc(conn, '无效选择', encoding)

    # 用户退出，从在线列表中移除
    remove_online_user(user)
    conn.close()

# 服务器主函数
def main():
    HOST, PORT = '0.0.0.0', 2323
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(10)
        print(f'FSBC论坛已启动 → telnet {HOST}:{PORT}')
        # 启动一个线程来监控在线用户
        def monitor_online_users():
            while True:
                time.sleep(60)  # 每分钟检查一次
                online_count = len(get_online_users())
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 当前在线用户：{online_count}")
        
        threading.Thread(target=monitor_online_users, daemon=True).start()
        
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == '__main__':
    main()