import base64
import json
import time
import datetime

import requests
from Crypto.Cipher import AES
from requests.exceptions import HTTPError

from email import encoders
from email.header import Header
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr
import smtplib

def _format_addr(s):
	name, addr = parseaddr(s)
	return formataddr((Header(name, 'utf-8').encode(), addr))

from_addr = 'xxxxxxxxxx@qq.com'#填入自己的邮箱
password = 'xxxxxxxxxxxxxxxxxxxx' # 填入邮箱授权码
smtp_server = 'smtp.qq.com'
now = datetime.datetime.now().replace(microsecond=0)
scheduled_time = datetime.timedelta(seconds=10)

def send_mail(email):
    server = smtplib.SMTP(smtp_server, 25)
#    server.set_debuglevel(1)
    server.login(from_addr, password)
    msg = MIMEText('哥，已经打卡成功！')
    msg['From'] = _format_addr('发件人 <%s>' % from_addr)
    msg['To'] = _format_addr('收件人 <%s>' % email)
    msg['Subject'] = Header('今日校园打卡')
    server.sendmail(from_addr, email, msg.as_string())
    server.quit()


def printLog(text: str) -> None:
    """Print log

    Print log with date and time and update last log,
    For example:

    # >>> printLog('test')
    [21-01-18 08:08:08]: test

    """
    global lastLog
    print(f'[{"%.2d-%.2d-%.2d %.2d:%.2d:%.2d" % time.localtime()[:6]}]: {text}')
    lastLog = text


def sendServerChan(key: str, text: str, description: str) -> bool:
    """Send a message through ServerChan

    Send a message with title and details through ServerChan. you can check the sent message through WeChat,
    the title will be fully displayed, however, you need to click the details button for details.

    Args:
      key:
        SCKEY for your serverChan
      text:
        The title of the message you want to send
      description:
        The detail of the message you want to send

    Return:
      True if sent successfully

    Raises:
      HTTPError from requests

    """
    messageData = {
        'text': text,
        'desp': description
    }
    sendResponse = requests.post(
        url=f'https://sc.ftqq.com/{key}.send',
        data=messageData
    )
    sendResponse.raise_for_status()

    if 'success' in sendResponse.text:
        printLog('发送Server酱成功。')
        return True
    printLog(f'发送Server酱失败：{sendResponse.text}')
    return False


def getConfig() -> dict:
    """Get the configuration from config.json in the current directory

    Return:
      configuration dict, for example:

      {
          "user": [
              {
                  "username": "201688888888",
                  "password": "888888",
                  "location": "Toilet, Home, China",
                  "serverChan": "xxx"
              },
              { ... More users ... }
          ]
      }

    """
    configFileName = 'config.json'
    configFile = open(configFileName, encoding='utf-8')
    configText = configFile.read()
    configFile.close()
    return json.loads(configText)


def encryptPassword(password: str, key: str) -> str:
    """Encrypt password

    Encrypt the password in ECB mode, PKCS7 padding, then Base64 encode the password

    Args:
      password:
        The password to encrypt
      key:
        The encrypt key for encryption

    Return:
      encryptedPassword:
        Encrypted password

    """
    # add padding
    blockSize = len(key)
    padAmount = blockSize - len(password) % blockSize
    padding = chr(padAmount) * padAmount
    encryptedPassword = password + padding

    # encrypt password in ECB mode
    aesEncryptor = AES.new(key.encode('utf-8'), AES.MODE_ECB)
    encryptedPassword = aesEncryptor.encrypt(encryptedPassword.encode('utf-8'))

    # base64 encode
    encryptedPassword = base64.b64encode(encryptedPassword)

    return encryptedPassword.decode('utf-8')


def login(username: str, password: str,email: str) -> bool:
    """Log in to cas of HFUT

    Try to log in with username and password. Login operation contains many jumps,
    there may be some unhandled problems, FUCK HFUT!

    Args:
      username:
        Username for HFUT account
      password:
        Password for HFUT account

    Return:
      True if logged in successfully

    Raises:
      HTTPError: When you are unlucky

    """
    # get cookie: SESSION
    ignore = requestSession.get('https://cas.hfut.edu.cn/cas/login')
    ignore.raise_for_status()

    # get cookie: JSESSIONID
    ignore = requestSession.get('https://cas.hfut.edu.cn/cas/vercode')
    ignore.raise_for_status()

    # get encryption key
    timeInMillisecond = round(time.time_ns() / 100000)
    responseForKey = requestSession.get(
        url='https://cas.hfut.edu.cn/cas/checkInitVercode',
        params={'_': timeInMillisecond})
    responseForKey.raise_for_status()

    encryptionKey = responseForKey.cookies['LOGIN_FLAVORING']

    # check if verification code is required
    if responseForKey.json():
        printLog('需要验证码，过一会再试试吧。')
        return False

    # try to login
    encryptedPassword = encryptPassword(password, encryptionKey)
    checkIdResponse = requestSession.get(
        url='https://cas.hfut.edu.cn/cas/policy/checkUserIdenty',
        params={'_': (timeInMillisecond + 1), 'username': username, 'password': encryptedPassword})
    checkIdResponse.raise_for_status()

    checkIdResponseJson = checkIdResponse.json()
    if checkIdResponseJson['msg'] != 'success':
        # login failed
        if checkIdResponseJson['data']['mailRequired'] or checkIdResponseJson['data']['phoneRequired']:
            # the problem may be solved manually
            printLog('需要进行手机或邮箱认证，移步: https://cas.hfut.edu.cn/')
            return False
        printLog(f'处理checkUserIdenty时出现错误：{checkIdResponseJson["msg"]}')
        return False
    requestSession.headers.update({'Content-Type': 'application/x-www-form-urlencoded'})

    loginResponse = requestSession.post(
        url='https://cas.hfut.edu.cn/cas/login',
        data={
            'username': username,
            'capcha': '',
            'execution': 'e1s1',
            '_eventId': 'submit',
            'password': encryptedPassword,
            'geolocation': "",
            'submit': "登录"
        })
    loginResponse.raise_for_status()



    send_mail(email)

    printLog('邮箱发送成功')

    requestSession.headers.pop('Content-Type')
    if 'cas协议登录成功跳转页面。' not in loginResponse.text:
        # log in failed
        printLog('登录失败')
        return False
    # log in success
    printLog('登录成功')
    return True


def submit(location: str) -> bool:
    """Submit using specific location

    submit today's form based on the form submitted last time using specific loaction

    Return:
      True if submitted successfully

    Args:
      location:
        Specify location information instead of mobile phone positioning

    Raises:
      HTTPError: Shit happens

    """
    ignore = requestSession.get(
        url='http://stu.hfut.edu.cn/xsfw/sys/swmxsyqxxsjapp/*default/index.do'
    )
    ignore.raise_for_status()

    requestSession.headers.update({
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Requested-With': 'XMLHttpRequest'
    })
    ignore = requestSession.post(
        url='http://stu.hfut.edu.cn/xsfw/sys/emapfunauth/welcomeAutoIndex.do'
    )
    ignore.raise_for_status()

    requestSession.headers.pop('Content-Type')
    requestSession.headers.pop('X-Requested-With')
    ignore = requestSession.get(
        url='http://stu.hfut.edu.cn/xsfw/sys/emapfunauth/casValidate.do',
        params={
            'service': '/xsfw/sys/swmjbxxapp/*default/index.do'
        }
    )
    ignore.raise_for_status()

    requestSession.headers.update({
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': 'http://stu.hfut.edu.cn/xsfw/sys/swmjbxxapp/*default/index.do'
    })
    ignore = requestSession.get(
        url='http://stu.hfut.edu.cn/xsfw/sys/emappagelog/config/swmxsyqxxsjapp.do'
    )
    ignore.raise_for_status()

    # get role config
    requestSession.headers.pop('X-Requested-With')
    requestSession.headers.update({
        'Content-Type': 'application/x-www-form-urlencoded'
    })
    configData = {
        'data': json.dumps({
            'APPID': '5811260348942403',
            'APPNAME': 'swmxsyqxxsjapp'
        })
    }
    roleConfigResponse = requestSession.post(
        url='http://stu.hfut.edu.cn/xsfw/sys/swpubapp/MobileCommon/getSelRoleConfig.do',
        data=configData
    )
    roleConfigResponse.raise_for_status()

    roleConfigJson = roleConfigResponse.json()
    if roleConfigJson['code'] != '0':
        # :(
        printLog(f'处理roleConfig时发生错误：{roleConfigJson["msg"]}')
        return False

    # get menu info
    menuInfoResponse = requestSession.post(
        url='http://stu.hfut.edu.cn/xsfw/sys/swpubapp/MobileCommon/getMenuInfo.do',
        data=configData
    )
    menuInfoResponse.raise_for_status()

    menuInfoJson = menuInfoResponse.json()

    if menuInfoJson['code'] != '0':
        # :(
        printLog(f'处理menuInfo时发生错误：{menuInfoJson["msg"]}')
        return False

    # get setting... for what?
    requestSession.headers.pop('Content-Type')
    settingResponse = requestSession.get(
        url='http://stu.hfut.edu.cn/xsfw/sys/swmxsyqxxsjapp/modules/mrbpa/getSetting.do',
        data={'data': ''}
    )
    settingResponse.raise_for_status()

    settingJson = settingResponse.json()

    # get the form submitted last time
    requestSession.headers.update({
        'Content-Type': 'application/x-www-form-urlencoded'
    })
    todayDateStr = "%.2d-%.2d-%.2d" % time.localtime()[:3]
    lastSubmittedResponse = requestSession.post(
        url='http://stu.hfut.edu.cn/xsfw/sys/swmxsyqxxsjapp/modules/mrbpa/getStuXx.do',
        data={'data': json.dumps({'TBSJ': todayDateStr})}
    )
    lastSubmittedResponse.raise_for_status()

    lastSubmittedJson = lastSubmittedResponse.json()

    if lastSubmittedJson['code'] != '0':
        # something wrong with the form submitted last time
        printLog('上次填报提交的信息出现了问题，本次最好手动填报提交。')
        return False

    # generate today's form to submit
    submitDataToday = lastSubmittedJson['data']
    submitDataToday.update({
        'BY1': '1',
        'DFHTJHBSJ': '',
        'DZ_SFSB': '1',
        'DZ_TBDZ': location,
        'GCJSRQ': '',
        'GCKSRQ': '',
        'TBSJ': todayDateStr
    })

    # try to submit
    submitResponse = requestSession.post(
        url='http://stu.hfut.edu.cn/xsfw/sys/swmxsyqxxsjapp/modules/mrbpa/saveStuXx.do',
        data={'data': json.dumps(submitDataToday)}
    )
    submitResponse.raise_for_status()

    submitResponseJson = submitResponse.json()

    if submitResponseJson['code'] != '0':
        # failed
        printLog(f'提交时出现错误：{submitResponseJson["msg"]}')
        return False

    # succeeded
    printLog('提交成功')
    requestSession.headers.pop('Referer')
    requestSession.headers.pop('Content-Type')
    return True


# main
userConfig = getConfig()
lastLog = ''

for i in userConfig['user']:
    # create a new session
    requestSession = requests.session()
    requestSession.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9'
    })

    printLog(f'开始处理用户{i["username"]}')
    try:
        # login and submit
        if login(i['username'], i['password'], i['email']) and submit(i['location']):
            if i['serverChan']:
                # has SCKEY, send success prompt
                sendServerChan(
                    key=i['serverChan'],
                    text='今日校园每日疫情填报成功',
                    description=f'用户{i["username"]}，你的今日校园每日疫情填报成功了！\
                    \n今天也是元气满满的一天！\n'
                )
            printLog('当前用户处理成功')
        else:
            # failed
            if i['serverChan']:
                # has SCKEY, send error message
                sendServerChan(
                    key=i['serverChan'],
                    text='今日校园每日疫情填报失败',
                    description=f'用户{i["username"]}，你的今日校园疫情填报失败：{lastLog}'
                )
            printLog('发生错误，终止当前用户的处理')
    except HTTPError as httpError:
        if i['serverChan']:
            # has SCKEY, send exception message
            sendServerChan(
                key=i['serverChan'],
                text='今日校园每日疫情填报发生异常',
                description=f'用户{i["username"]}，你的今日校园疫情填报时发生HTTP异常：{httpError}，建议手动登录查看实际填报情况'
            )
        print(f'发生HTTP错误：{httpError}，终止当前用户的处理')
        # process next user
        continue

printLog('所有用户处理结束')
#项目仅用作交流学习，其余后果自负
