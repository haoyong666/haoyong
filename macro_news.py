import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import json

# ===== 配置 =====
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
SEND_EMAIL = os.environ["SEND_EMAIL"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
RECEIVE_EMAIL = os.environ["RECEIVE_EMAIL"]

# ===== 1. 抓取新浪财经新闻（多抓些，留给 AI 筛选） =====
def fetch_sina_news(pages=3):
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
                    all_items.append({
                        "title": title,
                        "link": link,
                        "published": ctime
                    })
        except Exception as e:
            print(f"抓取失败(page {page}): {e}")
    # 去重
    seen = set()
    unique = []
    for item in all_items:
        if item["link"] not in seen:
            seen.add(item["link"])
            unique.append(item)
    return unique[:30]   # 取前30条给 AI

# ===== 2. 调用 DeepSeek 筛选并总结 =====
def filter_and_summarize(articles):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    if not articles:
        return "今日暂无新闻。", 0

    news_text = ""
    for i, a in enumerate(articles):
        news_text += f"{i+1}. [{a['title']}]({a['link']}) ({a['published']})\n"

    prompt = f"""当前北京时间：{now_str}。下面是新浪财经最新新闻列表。请你严格按照以下要求处理：
1. 只挑选与“政策、经济发展、重大科研成果”三类直接相关的新闻（不限国内国际）。
2. 最多选出 15 条（不足 15 条就只发实际数量，绝不编造）。
3. 每条新闻用一句话总结核心内容，字数严格限制在 50 字以内，并保留原文链接。
4. 输出格式：
   以下为今日宏观精选新闻，共X条（北京时间 {now_str}）
   1. [标题或总结](链接) （发布时间）
   ...
5. 如果一条符合的都没有，请回复“今日暂无相关新闻”。

{news_text}"""

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 1800
    }
    try:
        resp = requests.post("https://api.deepseek.com/v1/chat/completions",
                             headers=headers, json=data, timeout=60)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        # 统计条数
        import re
        count = len(re.findall(r'^\d+\.', content, re.MULTILINE))
        return content, min(count, 15)
    except Exception as e:
        print(f"DeepSeek 调用失败: {e}")
        return None, 0   # None 表示调用失败，触发备用方案

# ===== 3. 备用方案：直接发送原始新闻（无总结） =====
def fallback_raw(articles):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    if not articles:
        return "今日暂无新闻。", 0
    lines = [f"以下为今日宏观相关新闻（原始列表），共{len(articles)}条（北京时间 {now_str}）"]
    for i, a in enumerate(articles, 1):
        lines.append(f"{i}. [{a['title']}]({a['link']}) ({a['published']})")
    return "\n".join(lines), len(articles)

# ===== 4. 发送邮件 =====
def send_email(content, count):
    now = datetime.now()
    period = "早间" if now.hour < 11 else ("午间" if now.hour < 16 else "晚间")
    subject = f"📰 宏观精选 {period}简报（{count}条） - {now.strftime('%m-%d %H:%M')}"
    msg = MIMEMultipart("alternative")
    msg["From"] = SEND_EMAIL
    msg["To"] = RECEIVE_EMAIL
    msg["Subject"] = subject
    html = f"""<html><body style="font-family:Microsoft YaHei; font-size:15px; line-height:1.8;">
{content.replace(chr(10), '<br>')}
<br><hr>
<p style="color:gray; font-size:12px;">本邮件由AI筛选并总结，仅供参考，不构成投资建议。</p >
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

# ===== 主流程 =====
if __name__ == "__main__":
    print(f"[{datetime.now()}] 采集新浪新闻...")
    raw_articles = fetch_sina_news(pages=3)
    print(f"共采集 {len(raw_articles)} 条候选新闻")

    # 优先使用 AI 精选+总结
    report, count = filter_and_summarize(raw_articles)
    if report is None:
        print("AI 调用失败，使用原始新闻作为备用")
        report, count = fallback_raw(raw_articles[:15])

    send_email(report, count)
    print("结束。")
