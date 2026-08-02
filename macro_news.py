import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

# 配置（从 GitHub Secrets 读取）
SEND_EMAIL = os.environ["SEND_EMAIL"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
RECEIVE_EMAIL = os.environ["RECEIVE_EMAIL"]

def fetch_sina_news(pages=3):
    """获取新浪财经宏观/政策类滚动新闻（免费、无需Key、极稳定）"""
    all_items = []
    for page in range(1, pages+1):
        url = f"https://feed.mix.sina.com.cn/api/roll/get?pageid=155&lid=1686&k=&num=20&page={page}&r=0.1&callback="
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
            if data.get("result") and data["result"].get("data"):
                for item in data["result"]["data"]:
                    title = item.get("title", "").strip()
                    if not title:
                        continue
                    link = item.get("url", "")
                    ctime = item.get("ctime", "")
                    all_items.append(f"[{ctime}] {title} {link}")
            else:
                print(f"第{page}页无数据")
        except Exception as e:
            print(f"抓取失败(page {page}): {e}")
            continue
    # 去重（按链接）
    seen = set()
    unique = []
    for line in all_items:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    return unique[:15]  # 最多15条

# 抓取新闻
news_list = fetch_sina_news(pages=3)
count = len(news_list)
now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

if count > 0:
    body = f"以下为今日宏观相关新闻，共{count}条（北京时间 {now_str}）\n" + "\n".join([f"{i}. {item}" for i, item in enumerate(news_list, 1)])
else:
    body = "今日暂无新闻数据，请稍后重试。"

# 发送邮件
def send_email(content, count):
    now = datetime.now()
    period = "早间" if now.hour < 11 else ("午间" if now.hour < 16 else "晚间")
    subject = f"📰 宏观新闻 {period}简报（{count}条） - {now.strftime('%m-%d %H:%M')}"
    msg = MIMEMultipart("alternative")
    msg["From"] = SEND_EMAIL
    msg["To"] = RECEIVE_EMAIL
    msg["Subject"] = subject
    html = f"""<html><body style="font-family:Microsoft YaHei; font-size:15px; line-height:1.8;">
{content.replace(chr(10), '<br>')}
<br><hr>
<p style="color:gray; font-size:12px;">本邮件由自动化脚本生成，数据来源新浪财经，仅供参考。</p >
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
    print(f"[{datetime.now()}] 开始采集新浪财经新闻...")
    send_email(body, count)
    print("结束。")
