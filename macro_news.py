import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
SEND_EMAIL = os.environ["SEND_EMAIL"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
RECEIVE_EMAIL = os.environ["RECEIVE_EMAIL"]

def fetch_cls_news(max_count=30):
    """抓取财联社电报，返回原始新闻列表"""
    url = "https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=8.4.6"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.cls.cn/telegraph"}
    params = {"type": "telegram", "keyword": "", "page": 0, "pageSize": max_count}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        data = resp.json()
        if data.get("error") == 0 and "data" in data:
            articles = []
            for item in data["data"]:
                title = item.get("content", "").strip()
                if not title:
                    continue
                ctime = datetime.fromtimestamp(item.get("ctime", 0)).strftime("%m-%d %H:%M")
                link = f"https://www.cls.cn/detail/{item.get('id', '')}"
                articles.append(f"【{ctime}】{title[:100]} {link}")
            return articles[:max_count]
        else:
            print(f"财联社接口返回错误: {data}")
            return []
    except Exception as e:
        print(f"抓取失败: {e}")
        return []

# 采集
raw_lines = fetch_cls_news(30)
# 去重
seen = set()
news_list = []
for line in raw_lines:
    if line not in seen:
        seen.add(line)
        news_list.append(line)

# 直接取前15条作为邮件内容
top_news = news_list[:15]

if top_news:
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    body_lines = [f"以下为财联社实时电报前15条（北京时间 {now_str}）"]
    for i, item in enumerate(top_news, 1):
        body_lines.append(f"{i}. {item}")
    body = "\n".join(body_lines)
    count = len(top_news)
else:
    body = "今日暂无电报数据，请稍后重试。"
    count = 0

# 发送邮件
def send_email(content, count):
    now = datetime.now()
    period = "早间" if now.hour < 11 else ("午间" if now.hour < 16 else "晚间")
    subject = f"📰 宏观电报 {period}简报（{count}条） - {now.strftime('%m-%d %H:%M')}"
    msg = MIMEMultipart("alternative")
    msg["From"] = SEND_EMAIL
    msg["To"] = RECEIVE_EMAIL
    msg["Subject"] = subject
    html = f"""<html><body style="font-family:Microsoft YaHei; font-size:15px; line-height:1.8;">
{content.replace(chr(10), '<br>')}
<br><hr>
<p style="color:gray; font-size:12px;">本邮件由AI自动生成，仅供参考。</p >
</body></html>"""
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(SEND_EMAIL, EMAIL_PASSWORD)
        server.sendmail(SEND_EMAIL, [RECEIVE_EMAIL], msg.as_string())
        server.quit()
        print("邮件发送成功")
    except Exception as e:
        print(f"邮件发送失败: {e}")

if __name__ == "__main__":
    print(f"[{datetime.now()}] 抓取财联社电报...")
    send_email(body, count)
    print("结束。")
