import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import os

# ===== 配置（复用已有的 GitHub Secrets）=====
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
SEND_EMAIL = os.environ["SEND_EMAIL"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
RECEIVE_EMAIL = os.environ["RECEIVE_EMAIL"]

# ===== 1. 采集当天宏观新闻（经济、政治、政策等）=====
QUERIES = [
    "中国 经济 政策 OR 央行 OR 财政部 OR 统计局",
    "A股 利好 OR 股市 政策 OR 证监会",
    "地缘政治 OR 贸易 协议 OR 国际 关系",
    "美联储 OR 利率 OR 通胀 OR 就业",
    "产业政策 OR 新能源 OR 半导体 OR 基建",
    "一带一路 OR 区域合作 OR 外交",
    "PMI OR GDP OR 社融 OR 信贷",
    "国务院 常务会议 OR 发改委 OR 商务部",
]

def fetch_today_news(query, max_count=8):
    """从 Bing 抓取最近新闻，只保留昨天和今天的"""
    url = f"https://www.bing.com/news/search?q={requests.utils.quote(query)}&format=rss&cc=cn&setmkt=zh-CN&sortby=date"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        feed = feedparser.parse(r.text)
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        articles = []
        for entry in feed.entries[:max_count*2]:
            pub = entry.get("published", "")
            # 简单判断是否为近两天
            if today in pub or yesterday in pub or "小时前" in pub or "分钟前" in pub or "刚刚" in pub:
                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "published": pub,
                    "summary": entry.get("summary", "").replace('<div','').replace('</div>','').strip()
                })
            elif any(word in pub for word in ["2026", "2025"]):
                # 也保留明确今年日期的
                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "published": pub,
                    "summary": entry.get("summary", "").replace('<div','').replace('</div>','').strip()
                })
        return articles[:max_count]
    except Exception as e:
        print(f"抓取失败: {e}")
        return []

# ===== 2. 合并去重 =====
raw_news = []
for q in QUERIES:
    raw_news.extend(fetch_today_news(q, max_count=6))

# 按链接去重
seen = set()
unique_news = []
for n in raw_news:
    if n["link"] not in seen:
        seen.add(n["link"])
        unique_news.append(n)

# 限制总量，避免 token 过大
unique_news = unique_news[:60]

# ===== 3. 调用 DeepSeek 筛选15条并总结 =====
def generate_report(articles):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    if not articles:
        return "今日暂无相关宏观新闻。", 0

    news_text = ""
    for i, a in enumerate(articles):
        news_text += f"{i+1}. [{a['title']}]({a['link']}) ({a['published']})\n   {a['summary']}\n"

    prompt = f"""你是国内顶级财经媒体的主编。当前北京时间：{now_str}。
下面提供了今日可能影响国内股市的宏观新闻候选列表。请严格按以下要求整理简报：

1. 只从候选列表中挑选出与“经济、政治、政策、利于国内股市向好发展”直接相关的新闻，最多 **15 条**。如果符合条件的不足15条，就只输出实际数量，**绝对不要编造、不要补充旧知识**。
2. 按新闻重要性和时效性排序，最新最重要的放前面。
3. 每条新闻格式：标题（保留原文链接），然后用一句话总结核心要点，总结字数**严格控制在50字以内**（以中文计）。
4. 简报开头写明：“以下为今日宏观利好新闻，共 X 条”，并注明生成时间：{now_str}（北京时间）。
5. 如果候选列表中完全没有符合条件的新闻，请直接回复“今日无相关宏观新闻”。
6. 禁止使用任何内部知识库中的旧新闻。

候选新闻列表（共{len(articles)}条）：
{news_text}

请直接输出纯文本邮件内容，不要用代码块包裹。"""

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 2000
    }
    try:
        resp = requests.post("https://api.deepseek.com/v1/chat/completions",
                             headers=headers, json=data, timeout=90)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        # 简单统计条数（根据编号统计）
        count = content.count("\n1.") + content.count("\n2.")  # 粗略，但够用
        return content, count if count <= 15 else 15
    except Exception as e:
        print(f"DeepSeek 调用失败: {e}")
        return "AI总结生成失败，请检查网络或API余额。", 0

# ===== 4. 发送邮件 =====
def send_email(content, news_count):
    now = datetime.now()
    hour = now.hour
    period = "早间" if hour < 11 else ("午间" if hour < 16 else "晚间")
    subject = f"📰 宏观利好新闻 {period}简报（{news_count}条） - {now.strftime('%m-%d %H:%M')}"

    msg = MIMEMultipart("alternative")
    msg["From"] = SEND_EMAIL
    msg["To"] = RECEIVE_EMAIL
    msg["Subject"] = subject
    html = f"""<html><body style="font-family:Microsoft YaHei,sans-serif; font-size:15px; line-height:1.7;">
{content.replace(chr(10), '<br>')}
<br><hr>
<p style="color:gray; font-size:12px;">本邮件由AI自动生成，仅供参考，不构成投资建议。</p >
</body></html>"""
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(SEND_EMAIL, EMAIL_PASSWORD)
        server.sendmail(SEND_EMAIL, [RECEIVE_EMAIL], msg.as_string())
        server.quit()
        print("宏观新闻邮件发送成功")
    except Exception as e:
        print(f"邮件发送失败: {e}")

# ===== 主流程 =====
if __name__ == "__main__":
    print(f"[{datetime.now()}] 开始采集宏观新闻...")
    report, count = generate_report(unique_news)
    print(f"生成完毕，共 {count} 条新闻，正在发送邮件...")
    send_email(report, count)
    print("结束。")
