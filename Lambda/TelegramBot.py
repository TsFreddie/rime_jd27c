from dotenv import load_dotenv
import logging
import os
import JDTools
import Commands
import re
from bisect import bisect_left
from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove, ChatAction, ParseMode)
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, Filters
from git import Repo
import onedrivesdk
import urllib.request

load_dotenv()

# Onedrive Setup
redirect_uri = os.environ['ONEDRIVE_REDIRECT']
client_secret = os.environ['ONEDRIVE_SECRET']
client_id=os.environ['ONEDRIVE_CLIENTID']
api_base_url='https://api.onedrive.com/v1.0/'
scopes=['wl.signin', 'wl.offline_access', 'onedrive.readwrite']

http_provider = onedrivesdk.HttpProvider()
auth_provider = onedrivesdk.AuthProvider(
    http_provider=http_provider,
    client_id=client_id,
    scopes=scopes)

client = onedrivesdk.OneDriveClient(api_base_url, auth_provider, http_provider) 


ALLOWED_USER = set(os.environ['TELEGRAM_BOT_USER'].split(','))

updater = Updater(token=os.environ['TELEGRAM_BOT_TOKEN'], use_context=True)
dispatcher = updater.dispatcher

# def error_callback(update, context):
#     try:
#         context.user_data.clear()
#         raise context.error
#     except Exception as e:
#         print(e)

# dispatcher.add_error_handler(error_callback)

LOG_STATUS = []

def LOG(result = None):
    global LOG_STATUS

    if result is None:
        return "\n".join(LOG_STATUS)

    LOG_STATUS += result

def CLEAN(text):
    return (
        text.replace('*', '')
            .replace('__', '*')
            .replace('~`', ' =|=')
            .replace('`~', '=|= ')
            .replace('~', '')
            .replace('=|=', '~')
            .replace('(', '\(')
            .replace(')', '\)')
            .replace('`', ' ')
            .replace('-', '\-')
            .replace('>', '\>')
            .replace('<', '\<')
            .replace('.', '\.')
    )

def MARK(result):
    res = []
    for line in result:
        res.append(CLEAN(line))

    return res

def TYPING(update):
    update.message.chat.send_action(action = ChatAction.TYPING)

def REPLY(update, text, parse_mode=ParseMode.MARKDOWN_V2):
    update.message.reply_text(text=text, reply_markup=ReplyKeyboardRemove(), parse_mode=parse_mode)

def CHOOSE(update, text, choice, parse_mode=ParseMode.MARKDOWN_V2):
    update.message.reply_text(text=text, reply_markup=ReplyKeyboardMarkup(
        [choice, ['/取消']], one_time_keyboard=True), parse_mode=parse_mode)

# Help
def start(update, context):
    if update.effective_user.username not in ALLOWED_USER:
        return
    
    update.message.reply_text(text="""指令列表:
/add - 添加字词
/delete - 删除字词
/change - 修改字词
/rank - 字词排序
/list - 查看字词在码表的位置
/status - 查看当前修改
/drop - 放弃当前的修改
/pull - 从Github同步更新
/push - 保存并上传
/getjd - 获取键道6的新词
""")

# Fallback
def cancel(update, context):
    context.user_data.clear()
    REPLY(update, "操作已取消")
    return -1

# Commands
def add(update, context):
    if update.effective_user.username not in ALLOWED_USER:
        return -1

    data = update.message.text.split()
    if len(data) > 1:
        word = data[1]
        update.message.text = word
        if (len(word) > 1):
            return add_word(update, context)
        else:
            return add_char(update, context)

    REPLY(update, "请输入要添加的字/词")
    return 0

def delete(update, context):
    if update.effective_user.username not in ALLOWED_USER:
        return -1

    data = update.message.text.split()
    if len(data) > 1:
        word = data[1]
        update.message.text = word
        if (len(word) > 1):
            return delete_word(update, context)
        else:
            return delete_char(update, context)

    REPLY(update, "请输入要删除的字/词")
    return 3

def change(update, context):
    if update.effective_user.username not in ALLOWED_USER:
        return -1

    data = update.message.text.split()
    if len(data) > 1:
        word = data[1]
        update.message.text = word
        if (len(word) > 1):
            return change_word(update, context)
        else:
            return change_char(update, context)
        
    REPLY(update, "请输入要修改的字/词")
    return 6

def rank(update, context):
    if update.effective_user.username not in ALLOWED_USER:
        return -1

    data = update.message.text

    if 'rank_requested' not in context.user_data:
        context.user_data['rank_requested'] = True
        data = data.split()
        if (len(data) <= 1):
            REPLY(update, "请输入要排序的编码")
            return 9
        data = data[1]
    
    if 'rank_code' not in context.user_data:
        context.user_data['rank_code'] = data

        TYPING(update)

        zis = JDTools.get_zi_of_code(data)
        if len(zis) == 0:
            cis = JDTools.get_ci_of_code(data)
            if (len(cis) == 0):
                REPLY(update, "没有该编码")
                context.user_data.clear()
                return -1
            elif len(cis) == 1:
                REPLY(update, "编码无重码")
                context.user_data.clear()
                return -1
            else:
                context.user_data['rank_type'] = 'word'
                CHOOSE(update, "请选择需要提权的词", [ci.word() for ci in cis])
        elif len(zis) == 1:
            REPLY(update, "编码无重码")
            context.user_data.clear()
            return -1
        else:
            context.user_data['rank_type'] = 'char'
            CHOOSE(update, "请选择需要提权的字", [zi.char() for zi in zis])
    elif 'rank_word' not in context.user_data:
        context.user_data['rank_word'] = data
        code = context.user_data['rank_code']
        rank_type = context.user_data['rank_type']

        TYPING(update)

        if (rank_type == 'word'):
            ci = JDTools.get_word(data)
            if ci is None:
                REPLY(update, "未知错误")
                context.user_data.clear()
                return -1

            codes = list(filter(lambda c : c[1] == code, JDTools.ci2codes(ci)))
            if (len(codes) == 0):
                REPLY(update, "未知错误")
                context.user_data.clear()
                return -1

            context.user_data['rank_pinyin'] = codes[0][-1]
            CHOOSE(update, "确定要提升 %s 词 \(%s\) 至首位吗" % (data, code), ['是的'])
        else:
            zi = JDTools.get_char(data)
            if zi is None:
                REPLY(update, "未知错误")
                context.user_data.clear()
                return -1

            codes = list(filter(lambda c : c[1] == code, JDTools.zi2codes(zi)))
            if (len(codes) == 0):
                REPLY(update, "未知错误")
                context.user_data.clear()
                return -1

            context.user_data['rank_pinyin'] = codes[0][-1]
            CHOOSE(update, "确定要提升 %s 字全码 \(%s\) 至首位吗" % (data, code), ['是的'])
    else:
        word = context.user_data['rank_word']
        pinyin = context.user_data['rank_pinyin']
        code = context.user_data['rank_code']
        rank_type = context.user_data['rank_type']

        TYPING(update)

        if (rank_type == 'word'):
            result = MARK(Commands.safe_rank_word(word, pinyin, code, 1))
        else:
            result = MARK(Commands.safe_rank_char(word, pinyin, code, 1))

        REPLY(update, "\n".join(result))
        context.user_data.clear()

        LOG(result)

        return -1

    return 9

def status(update, context):
    if update.effective_user.username not in ALLOWED_USER:
        return -1

    if (len(LOG_STATUS) == 0):
        REPLY(update, "无变化")
        return -1
    REPLY(update, "\n".join(LOG_STATUS))
    return -1

def pull(update, context):
    if update.effective_user.username not in ALLOWED_USER:
        return -1

    if (len(LOG_STATUS) > 0):
        REPLY(update, "\n".join(LOG_STATUS))
        REPLY(update, '有未提交修改，请先Push或Drop当前修改')
        return -1

    TYPING(update)
    repo = Repo('.').git
    REPLY(update, 'Pull完成 %s' % repo.pull(), ParseMode.HTML)
    JDTools.reset()
    return -1
    
def push(update, context):
    if update.effective_user.username not in ALLOWED_USER:
        return -1

    if 'requested_code' not in context.user_data:
        REPLY(update, '正在构建，请稍候\.\.\.')

        TYPING(update)
        
        try:
            JDTools.commit()
            LOG_STATUS.clear()

            repo = Repo('.').git

            changes = repo.status('--porcelain').strip()
            if (len(changes) > 0):
                repo.add('-A')
                repo.commit(m="自动更新码表")
                repo.push()

                REPLY(update, '构建完毕，Push成功')
            else:
                REPLY(update, '构建完毕，码表无改动')
        except Exception as e:
            REPLY(update, '构建失败')
            raise e
            return -1

        TYPING(update)

        try:
            # try load session
            auth_provider.load_session()
            auth_provider.refresh_token()
        except:
            # get new session
            auth_url = client.auth_provider.get_auth_url(redirect_uri)
            REPLY(update, "请登录OneDrive:\n %s\n并输入CODE" % auth_url, ParseMode.HTML)
            context.user_data['requested_code'] = True
            return 12
    else:
        context.user_data.clear()
        code = update.message.text
        try:
            client.auth_provider.authenticate(code, redirect_uri, client_secret)
            auth_provider.save_session()
        except:
            REPLY(update, "OneDrive登录失败")
            return -1

    try:
        TYPING(update)
        client.item(drive='me', path=os.environ['ONEDRIVE_PATH']).children['xkjd27c.cizu.dict.yaml'].upload('./rime/xkjd27c.cizu.dict.yaml')
        client.item(drive='me', path=os.environ['ONEDRIVE_PATH']).children['xkjd27c.danzi.dict.yaml'].upload('./rime/xkjd27c.danzi.dict.yaml')
        client.item(drive='me', path=os.environ['ONEDRIVE_PATH']).children['xkjd27c.chaojizici.dict.yaml'].upload('./rime/xkjd27c.chaojizici.dict.yaml')
        REPLY(update, "OneDrive上传成功")
    except Exception as e:
        REPLY(update, "OneDrive上传失败: \n%s" % e, ParseMode.HTML)

    return -1

def binary_search(arr, low, high, x): 
    if high >= low: 
        mid = (high + low) // 2
        if arr[mid][1] == x: 
            return mid 
        elif arr[mid][1] > x: 
            return binary_search(arr, low, mid - 1, x) 
        else: 
            return binary_search(arr, mid + 1, high, x) 
    else: 
        return -1

def list_code(data, code, update):
    index = binary_search(data, 0, len(data), code)
    if (index > 0):
        start = min(len(data) - 5, max(index - 2, 0))
        result = []
        for i in range(max(start, 0), min(start + 5, len(data))):
            if i == index:
                result.append("\-\>" + data[i][1].ljust(8) + data[i][0])
            else:
                result.append("  " + data[i][1].ljust(8) + data[i][0])
        REPLY(update, "```\n%s\n```" % "\n".join(result))
        return True
    return False

def list_command(update, context):
    if update.effective_user.username not in ALLOWED_USER:
        return -1

    if 'list_requested' not in context.user_data:
        data = update.message.text.split()
        context.user_data['list_requested'] = True

        if len(data) > 1:
            word = data[1]
            update.message.text = word
            return list_command(update, context)

        REPLY(update, "请输入要查找的字/词/编码")
    else:
        TYPING(update)
        data = update.message.text
        printed = False
        if re.search('^[a-z;]{1,6}$', data):
            zi_entries, _ = JDTools.get_current_danzi_codes()
            ci_entries, _ = JDTools.get_current_cizu_codes()
            printed = list_code(zi_entries, data, update) or list_code(ci_entries, data, update) or printed
        else:
            if len(data) == 1:
                codes = JDTools.gen_char(data)
                for code in codes:
                    zi_entries, _ = JDTools.get_current_danzi_codes()
                    printed = list_code(zi_entries, code[1], update) or printed
            else:
                codes = JDTools.gen_word(data)
                for code in codes:
                    ci_entries, _ = JDTools.get_current_cizu_codes()
                    printed = list_code(ci_entries, code[1], update) or printed
        
        if not printed:
            REPLY(update, '找不到编码')
        context.user_data.clear()
        return -1
    
    return 10

def drop(update, context):
    if update.effective_user.username not in ALLOWED_USER:
        return -1

    if 'drop_requested' not in context.user_data:
        context.user_data['drop_requested'] = True

        if (len(LOG_STATUS) == 0):
            REPLY(update, "无变化")
            return -1
        
        REPLY(update, "\n".join(LOG_STATUS))

        CHOOSE(update, "确定要放弃所有修改吗", ['是的'])
        return 11
    else:
        context.user_data.clear()
        LOG_STATUS.clear()
        JDTools.reset()
        REPLY(update, "所有修改已还原")
        return -1

def add_word(update, context):
    data = update.message.text

    if 'adding_word' not in context.user_data:
        context.user_data['adding_word'] = data
        REPLY(update, "正在添加词：%s，请提供编码" % data)
        return 1

    elif 'adding_word_wanted' not in context.user_data:
        word = context.user_data['adding_word']
        code = data.strip()
        context.user_data['adding_word_wanted'] = code

        pinyins = JDTools.find_word_pinyin_of_code(word, code)
        if (len(pinyins) == 0):
            REPLY(update, "无法添加，可能音码有误")
            context.user_data.clear()
            return -1

        if (len(pinyins) == 1):
            update.message.text = pinyins[0]
            return add_word(update, context)
        
        if (len(pinyins) > 4):
            REPLY(update, "无法确定读音，请提供全拼读音")
        else:
            CHOOSE(update, "请选择一个拼音", pinyins)

    elif 'adding_word_pinyin' not in context.user_data:
        pinyin = data.strip()
        word = context.user_data['adding_word']
        wanted_code = context.user_data['adding_word_wanted']
        context.user_data['adding_word_pinyin'] = pinyin

        TYPING(update)

        ci = JDTools.get_word(word)
        if (ci is not None and tuple(pinyin.split(' ')) in ci.pinyins()):
            REPLY(update, "该词已有拼音\(%s\)，已取消操作。" % pinyin)
            context.user_data.clear()
            return -1

        space_data = JDTools.find_space_for_word(word, pinyin)
        if space_data is None:
            REPLY(update, "未知错误")
            context.user_data.clear()
            return -1

        codes, spaces, dup = space_data
        
        wanted_correct = False
        for code in codes:
            if code.startswith(wanted_code):
                wanted_correct = True
        
        if not wanted_correct:
            fix_code = codes[0][:len(wanted_code)]
            REPLY(update, "提供的编码笔码\(%s\)可能有误\n已自动修正为: %s" % (wanted_code, fix_code))
            wanted_code = fix_code
        
        min_recommend = 6
        for space in spaces:
            if len(word) == 3 or space > 3:
                min_recommend = min(min_recommend, space)

        if min_recommend > len(wanted_code) and min_recommend == 6:
            REPLY(update, "您提供的编码可能有重码，只有6码空间可用，6码有%d重码。" % (dup))
        elif min_recommend > len(wanted_code):
            REPLY(update, "您提供的编码可能有重码，推荐使用%d码。" % (min_recommend))
        elif min_recommend < len(wanted_code):
            REPLY(update, "该词可以使用更短的%d码。" % (min_recommend))
        else:
            update.message.text = wanted_code
            return add_word(update, context)

        CHOOSE(update, "请确认想要的码长", [wanted_code, codes[0][:min_recommend]])

    elif 'adding_word_code' not in context.user_data:
        context.user_data['adding_word_code'] = data.strip('*')
        CHOOSE(update, "加哪个码表", ['通常', '超级'])

    elif 'adding_word_which' not in context.user_data:
        word = context.user_data['adding_word']
        pinyin = context.user_data['adding_word_pinyin']
        code = context.user_data['adding_word_code']
        which = 1 if data == '通常' else 2
        context.user_data['adding_word_which'] = which

        REPLY(update, "向 %s 码表里添加 %s 词\n拼音：%s\n编码：%s" % (data, word, pinyin, code))
        CHOOSE(update, "确定要添加吗", ['是的'])

    else:
        word = context.user_data['adding_word']
        pinyin = context.user_data['adding_word_pinyin']
        code = context.user_data['adding_word_code']
        which = context.user_data['adding_word_which']

        TYPING(update)

        result = MARK(Commands.safe_add_word(which, word, pinyin, code))
        REPLY(update, "\n".join(result))
        context.user_data.clear()

        LOG(result)

        return -1

    return 1

def add_char(update, context):
    data = update.message.text

    if 'adding_char' not in context.user_data:
        context.user_data['adding_char'] = data
        REPLY(update, "正在添加字：%s，请提供拆字" % data)
        return 2

    elif 'adding_char_shape' not in context.user_data:
        context.user_data['adding_char_shape'] = JDTools.code2shape(data)
        REPLY(update, "请提供拼音")

    elif 'adding_char_pinyin' not in context.user_data:
        context.user_data['adding_char_pinyin'] = data
        shape = context.user_data['adding_char_shape']
        
        TYPING(update)
        
        space_data = JDTools.find_space_for_char(JDTools.s(shape), data)
        if space_data is None:
            REPLY(update, "无法添加")
            context.user_data.clear()
            return -1
    
        codes, spaces, dup = space_data
        context.user_data['adding_char_fullcode'] = codes[0]

        REPLY(update, "全码：%s\n可用码长：%s\n全码重码：%d" % (str(codes), str(spaces), dup))
        CHOOSE(update, "请选择一个码长（推荐\*）", ["%s%s" % (codes[0][:i], '*' if i in spaces else '') for i in range(2, 7)])
    
    elif 'adding_char_code' not in context.user_data:
        context.user_data['adding_char_code'] = data.strip('*')
        CHOOSE(update, "加哪个码表", ['通常', '超级'])
 
    elif 'adding_char_which' not in context.user_data:
        char = context.user_data['adding_char']
        pinyin = context.user_data['adding_char_pinyin']
        code = context.user_data['adding_char_code']
        fullcode = context.user_data['adding_char_fullcode']
        which = 1 if data == '通常' else 2
        context.user_data['adding_char_which'] = which

        REPLY(update, "向 %s 码表里添加 %s 字 \(%s\)" % (data, char, "%s/%s" % (fullcode, code) if fullcode != code else fullcode))
        CHOOSE(update, "确定要添加吗", ['是的'])

    else:
        char = context.user_data['adding_char']
        pinyin = context.user_data['adding_char_pinyin']
        code = context.user_data['adding_char_code']
        fullcode = context.user_data['adding_char_fullcode']
        which = context.user_data['adding_char_which']

        TYPING(update)

        result = MARK(Commands.safe_add_char(which, char, pinyin, "%s/%s" % (fullcode, code) if fullcode != code else fullcode))
        REPLY(update, "\n".join(result))
        context.user_data.clear()

        LOG(result)
        return -1

    return 2

def delete_word(update, context):
    data = update.message.text
    if 'deleteing_word' not in context.user_data:
        context.user_data['deleteing_word'] = data
        TYPING(update)

        ci = JDTools.get_word(data)
        if (ci is None):
            REPLY(update, '%s 词不存在' % data)
            context.user_data.clear()
            return -1
        
        pinyins = list(ci.pinyins())
        if len(pinyins) == 1:
            context.user_data['deleteing_word_pinyin'] = " ".join(pinyins[0])
            REPLY(update, "彻底删除 %s 词" % (context.user_data['deleteing_word']))
            CHOOSE(update, '确定要删除吗', ['是的'])
        else:
            CHOOSE(update, '请选择要删除的读音', [" ".join(pinyin) for pinyin in pinyins])

    elif 'deleteing_word_pinyin' not in context.user_data:
        context.user_data['deleteing_word_pinyin'] = data
        REPLY(update, "删除 %s 词读音 %s" % (context.user_data['deleteing_word'], data))
        CHOOSE(update, '确定要删除吗', ['是的'])

    else:
        word = context.user_data['deleteing_word']
        pinyin = context.user_data['deleteing_word_pinyin']

        TYPING(update)

        result = MARK(Commands.safe_delete_word(word, pinyin))
        REPLY(update, "\n".join(result))
        context.user_data.clear()

        LOG(result)
        return -1

    return 4

def delete_char(update, context):
    data = update.message.text
    if 'deleteing_char' not in context.user_data:
        context.user_data['deleteing_char'] = data
        TYPING(update)

        zi = JDTools.get_char(data)
        if (zi is None):
            REPLY(update, '%s 字不存在' % data)
            context.user_data.clear()
            return -1
        
        pinyins = list(zi.pinyins())
        if len(pinyins) == 1:
            context.user_data['deleteing_char_pinyin'] = pinyins[0]
            REPLY(update, "彻底删除 %s 字" % (context.user_data['deleteing_char']))
            CHOOSE(update, '确定要删除吗', ['是的'])
        else:
            CHOOSE(update, '请选择要删除的读音', pinyins)

    elif 'deleteing_char_pinyin' not in context.user_data:
        context.user_data['deleteing_char_pinyin'] = data
        REPLY(update, "删除 %s 字读音 %s" % (context.user_data['deleteing_char'], data))
        CHOOSE(update, '确定要删除吗', ['是的'])

    else:
        char = context.user_data['deleteing_char']
        pinyin = context.user_data['deleteing_char_pinyin']

        TYPING(update)

        result = MARK(Commands.safe_delete_char(char, pinyin))
        REPLY(update, "\n".join(result))
        context.user_data.clear()

        LOG(result)
        return -1
        
    return 5

def change_word(update, context):
    data = update.message.text

    def choose_length():
        word = context.user_data['changing_word']
        pinyin = context.user_data['changing_word_pinyin']
        
        space_data = JDTools.find_space_for_word(word, pinyin)
        if space_data is None:
            REPLY(update, "无法添加")
            context.user_data.clear()
            return -1

        codes, spaces, dup = space_data

        REPLY(update, "全码：%s\n可用码长：%s\n全码重码：%d" % (str(codes), str(spaces), dup))
        CHOOSE(update, "请选择一个码长（推荐\*）", ["%s%s" % (codes[0][:i], '*' if i in spaces else '') for i in range(3, 7)])
        return 7

    if 'changing_word' not in context.user_data:
        context.user_data['changing_word'] = data
        TYPING(update)

        ci = JDTools.get_word(data)
        if (ci is None):
            REPLY(update, '%s 词不存在' % data)
            context.user_data.clear()
            return -1

        pinyins = {}
        for code in JDTools.ci2codes(ci):
            ma = code[1]
            py = code[-1]
            if (py in pinyins):
                pinyins[py].append(ma)
            else:
                pinyins[py] = [ma]

        pinyins = list(pinyins.items())
        if len(pinyins) == 1:
            context.user_data['changing_word_pinyin'] = pinyins[0][0]
            return choose_length()
        else:
            CHOOSE(update, '请选择要更改长度的编码', [("%s\n%s" % ("/".join(pinyin[1]), pinyin[0])) for pinyin in pinyins])
    elif 'changing_word_pinyin' not in context.user_data:
        data = data.split('\n')
        if (len(data) < 2):
            REPLY(update, '操作已取消')
            context.user_data.clear()
            return -1
        
        context.user_data['changing_word_pinyin'] = data[1]
        return choose_length()
    elif 'changing_word_code' not in context.user_data:
        data = data.strip('*')
        context.user_data['changing_word_code'] = data
        REPLY(update, "变更 %s 词码长 \-\> %s" % (context.user_data['changing_word'], data))
        CHOOSE(update, '确定要修改吗', ['是的'])
    else:
        word = context.user_data['changing_word']
        pinyin = context.user_data['changing_word_pinyin']
        code = context.user_data['changing_word_code']

        TYPING(update)

        result = MARK(Commands.safe_change_word(word, pinyin, code))
        REPLY(update, "\n".join(result))
        context.user_data.clear()

        LOG(result)
        return -1
    
    return 7


def change_char(update, context):
    data = update.message.text

    def choose_length():
        char = context.user_data['changing_char']
        pinyin = context.user_data['changing_char_pinyin']
        zi = JDTools.get_char(char)
        if (zi is None):
            REPLY(update, '%s 字不存在' % char)
            context.user_data.clear()
            return -1

        space_data = JDTools.find_space_for_char(s(zi.shape()), pinyin)
        if space_data is None:
            REPLY(update, "无法添加")
            context.user_data.clear()
            return -1
    
        codes, spaces, dup = space_data
        context.user_data['changing_char_fullcode'] = codes[0]

        REPLY(update, "全码：%s\n可用码长：%s\n全码重码：%d" % (str(codes), str(spaces), dup))
        CHOOSE(update, "请选择一个码长（推荐\*）", ["%s%s" % (codes[0][:i], '*' if i in spaces else '') for i in range(2, 7)])
        return 8

    if 'changing_char' not in context.user_data:
        context.user_data['changing_char'] = data
        CHOOSE(update, "需要修改什么", ['笔码', '码长'])
    
    elif 'changing_char_type' not in context.user_data:
        context.user_data['changing_char_type'] = data
        char = context.user_data['changing_char']
        if (data == '笔码'):
            zi = JDTools.get_char(char)
            if (zi is None):
                REPLY(update, '%s 字不存在' % char)
                context.user_data.clear()
                return -1
            REPLY(update, "请输入 %s 字笔码，当前：%s" % (char, JDTools.s(zi.shape())))
        elif (data == '码长'):
            zi = JDTools.get_char(char)
            if (zi is None):
                REPLY(update, '%s 字不存在' % char)
                context.user_data.clear()
                return -1

            pinyins = {}
            for code in JDTools.zi2codes(zi):
                ma = code[1]
                py = code[-1]
                if (py in pinyins):
                    pinyins[py].append(ma)
                else:
                    pinyins[py] = [ma]

            pinyins = list(pinyins.items())
            if len(pinyins) == 1:
                context.user_data['changing_char_pinyin'] = pinyins[0][0]
                return choose_length()
            else:
                CHOOSE(update, '请选择要更改长度的编码', [("%s\n%s" % ("/".join(pinyin[1]), pinyin[0])) for pinyin in pinyins])
        else:
            REPLY(update, '操作已取消')
            context.user_data.clear()
            return -1
    elif context.user_data['changing_char_type'] == '笔码':
        if 'changing_char_shape' not in context.user_data:
            context.user_data['changing_char_shape'] = JDTools.code2shape(data)
            char = context.user_data['changing_char']
            zi = JDTools.get_char(char)
            if (zi is None):
                REPLY(update, '%s 字不存在' % char)
                context.user_data.clear()
                return -1

            pinyin = list(zi.pinyins())[0]
            context.user_data['changing_char_pinyin'] = pinyin
            codes = list(JDTools.char2codes(data, pinyin, 6, False, True))
            if (len(codes) == 0):
                REPLY(update, "无法添加")
                context.user_data.clear()
                return -1
            context.user_data['changing_char_code'] = codes[0]
            REPLY(update, "变更 %s 字笔码 %s \-\> %s" % (context.user_data['changing_char'], JDTools.s(zi.shape()), data))
            CHOOSE(update, '确定要修改吗', ['是的'])

        else:
            char = context.user_data['changing_char']
            pinyin = context.user_data['changing_char_pinyin']
            code = context.user_data['changing_char_code']

            TYPING(update)

            result = MARK(Commands.safe_change_char(char, pinyin, code))
            REPLY(update, "\n".join(result))
            context.user_data.clear()

            LOG(result)
            return -1
        
    elif context.user_data['changing_char_type'] == '码长':
        if 'changing_char_pinyin' not in context.user_data:
            data = data.split('\n')
            if (len(data) < 2):
                REPLY(update, '操作已取消')
                context.user_data.clear()
                return -1
            
            context.user_data['changing_char_pinyin'] = data[1]
            return choose_length()
        elif 'changing_char_code' not in context.user_data:
            data = data.strip('*')
            context.user_data['changing_char_code'] = data
            REPLY(update, "变更 %s 字码长 \-\> %s" % (context.user_data['changing_char'], data))
            CHOOSE(update, '确定要修改吗', ['是的'])
        else:
            char = context.user_data['changing_char']
            pinyin = context.user_data['changing_char_pinyin']
            code = context.user_data['changing_char_code']
            fullcode = context.user_data['changing_char_fullcode']

            TYPING(update)

            result = MARK(Commands.safe_change_char(char, pinyin, "%s/%s" % (fullcode, code) if fullcode != code else fullcode))
            REPLY(update, "\n".join(result))
            context.user_data.clear()

            LOG(result)
            return -1
    else:
        REPLY(update, '操作已取消')
        context.user_data.clear()
        return -1
    
    return 8

def getjd(update, context):
    TYPING(update)

    refuse_list = set()

    static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CiDB')
    with open(os.path.join(static_path, "拒绝.txt"), mode='r', encoding='utf-8') as infile:
        for line in infile:
            refuse_list.add(line.strip())

    jd6_words = set()
    jdc_words = set(ci.word() for ci in JDTools.get_all_ci())

    with urllib.request.urlopen('https://raw.githubusercontent.com/xkinput/Rime_JD/master/Tools/TermsTools/cizu.txt') as f:
        data = f.read().decode('utf-8')
        lines = data.split('\n')
        for line in lines:
            line = line.strip()
            if '\t' in line:
                word = line.split('\t')[0]
                jd6_words.add(word)

    jd6_diff = jd6_words.difference(jdc_words).difference(refuse_list)

    REPLY(update, ("键道6新词：\n" + CLEAN("\n".join(sorted(jd6_diff)))) if len(jd6_diff) > 0 else "无新词")

def default_message(update, context):
    data = update.message.text

    if (re.match('^[a-z;]{1,6}$', data)) or JDTools.get_char(data) is not None or JDTools.get_word(data) is not None:
        update.message.text = "/list " + data
        return list_command(update, context)
    else:
        update.message.text = "/add " + data
        return add(update, context)

add_convers = ConversationHandler(
    entry_points=[
        CommandHandler('add', add),
        CommandHandler('delete', delete),
        CommandHandler('change', change),
        CommandHandler('rank', rank),
        CommandHandler('list', list_command),
        CommandHandler('drop', drop),
        CommandHandler('push', push),
        CommandHandler('status', status),
        CommandHandler('pull', pull),
        CommandHandler('getjd', getjd),
        CommandHandler('start', start),
        MessageHandler(Filters.command, cancel),
        MessageHandler(Filters.all, default_message)
    ],
    states={
        0: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.regex('^.$'), add_char), MessageHandler(Filters.all, add_word)],
        1: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.all, add_word)],
        2: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.all, add_char)],
        3: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.regex('^.$'), delete_char), MessageHandler(Filters.all, delete_word)],
        4: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.all, delete_word)],
        5: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.all, delete_char)],
        6: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.regex('^.$'), change_char), MessageHandler(Filters.all, change_word)],
        7: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.all, change_word)],
        8: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.all, change_char)],
        9: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.all, rank)],
        10: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.all, list_command)],
        11: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.all, drop)],
        12: [MessageHandler(Filters.regex('^(/取消|/cancel)$'), cancel), MessageHandler(Filters.all, push)],
    },
    fallbacks=[CommandHandler('cancel', cancel)]
)


# Add Handlers
dispatcher.add_handler(add_convers)

updater.start_polling()
updater.idle()