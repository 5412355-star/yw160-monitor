# -*- coding: utf-8 -*-
"""
160加工网 云端监控（GitHub Actions 版）
每10分钟检查一次"手工活外发/外发加工"新帖子，筛选重点单，微信推送（Server酱）。
只依赖 Python 标准库，不需要安装任何第三方库。

推送配额说明：Server酱免费版每天5条，本脚本只推送优先级最高的单，
其余命中单只记日志，不浪费配额。
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, "state.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
LIST_URL = "https://www.yw160.com/category-catid-{cid}.html"
DETAIL_URL = "https://www.yw160.com/information-id-{iid}.html"

# 每天最多推送条数（Server酱免费额度）
DAILY_PUSH_LIMIT = 5

KEYWORDS = ["串珠", "穿珠", "穿珠子", "手工活", "发饰", "蝴蝶结", "挂圈", "弯针",
            "编织", "包装", "组装", "发箍", "大肠圈", "分钻", "钻石画", "打胶",
            "绕绳", "粘珍珠", "扎蝴蝶结"]
SCAM_WORDS = ["押金", "保证金", "材料费", "加盟费", "培训费", "预存", "会员费", "优先抢单"]
GOOD_REGION = ["发外地", "外地本地均可", "可发外地", "外地均可", "不限地区", "区域不限",
               "发江西", "发河南", "发全国", "本外地均可"]
BAD_REGION = ["限义乌", "外地勿扰", "义乌附近", "义乌本地", "东阳附近", "义乌江东",
              "廿三里", "义乌城西", "义乌荷叶塘", "义亭", "苏溪", "东阳江北", "义乌上溪"]
FACTORY_WORDS = ["找加工厂", "寻找加工厂", "找工厂", "找厂家", "寻找工厂", "需工厂",
                 "车间承包", "固定场地", "固定工人", "机器", "设备齐全", "有厂房"]
PROCUREMENT = ["求购", "采购", "需采购", "需要采购", "寻找现货", "找现货", "要现货",
               "需要现货", "有模具", "毛坯现货", "现需求购", "现货"]
PROCUREMENT_STRONG = ["求购", "需采购", "需要采购", "寻找现货", "找现货", "要现货",
                      "需要现货", "有模具", "毛坯现货", "现需求购", "采购现货"]
CATIDS = ["34", "1"]


def log(msg):
    print(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(msg), flush=True)


def fetch(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
            if raw[:3] == b"\xef\xbb\xbf":
                raw = raw[3:]
            return raw.decode("utf-8", errors="replace")
        except Exception as e:
            if i == tries - 1:
                log(f"抓取失败 {url}: {e}")
                return ""
            time.sleep(3)
    return ""


def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen": [], "push_date": "", "push_count": 0}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_list(text):
    items = re.findall(r'information-id-(\d+)\.html"[^>]*>([^<]{1,100})<', text)
    out, seen = [], set()
    for iid, title in items:
        t = clean(title)
        t = re.sub(r"^【(图|推荐)】\s*", "", t)
        if iid not in seen and t and "广告位" not in t and "郑重声明" not in t:
            seen.add(iid)
            out.append((iid, t))
    return out


def parse_detail(text):
    title = ""
    m = re.search(r"<title>([^<]+)</title>", text)
    if m:
        title = clean(m.group(1))
        title = re.sub(r"\s*-[^-]*-义乌160加工网$", "", title)
        title = re.sub(r"^【图】\s*", "", title)
    body = ""
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', text, re.I)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']description["\']', text, re.I)
    if m:
        body = clean(m.group(1))
    if not body:
        # 退路：正文截断
        t2 = re.sub(r"(?is)<head.*?</head>", " ", text)
        t2 = re.sub(r"(?is)<script.*?</script>", " ", t2)
        t2 = re.sub(r"<[^>]+>", " ", t2)
        t2 = re.sub(r"\s+", " ", t2)
        for mark in ["联系我时", "温馨提示", "您可能感兴趣", "相关分类"]:
            i = t2.find(mark)
            if i > 0:
                t2 = t2[:i]
                break
        body = t2.strip()
    return title, body


def hit(text, words):
    return any(w in text for w in words)


def strip_denial(text):
    text = re.sub(r"[无不免未](?:交|收|要|需|用|缴|付|收)?(?:押金|保证金|材料费|加盟费|培训费|会员费|预存)", "", text)
    text = re.sub(r"(?:不需要|不用|不用交|无需|不用收|不收取|无任何)\s*(?:押金|保证金|材料费|加盟费|培训费|会员费|预存)", "", text)
    return text


def main():
    key = (os.environ.get("SENDKEY") or "").strip()
    if not key:
        log("未设置 SENDKEY 环境变量，无法推送（仅记录）")

    state = load_state()
    seen = set(state.get("seen", []))

    # 1) 抓列表
    items = []
    for cid in CATIDS:
        text = fetch(LIST_URL.format(cid=cid))
        if not text:
            continue
        for iid, title in parse_list(text):
            if iid not in seen:
                items.append((iid, title))
        log(f"分类 {cid} 已抓取")
    if not items:
        log("无新帖")
        save_state(state)
        return
    uniq = {}
    for iid, title in items:
        uniq.setdefault(iid, title)
    items = sorted(uniq.items(), key=lambda x: int(x[0]), reverse=True)
    log(f"新帖 {len(items)} 条")

    # 2) 详情+筛选
    matched = []
    for iid, title in items:
        text = fetch(DETAIL_URL.format(iid=iid))
        seen.add(iid)
        if not text:
            continue
        dtitle, body = parse_detail(text)
        phones = sorted(set(re.findall(r"1[3-9]\d{9}", body)))
        full = title + " " + body
        if not (hit(title, KEYWORDS) or hit(body, KEYWORDS)):
            continue
        if hit(title, PROCUREMENT) or hit(body, PROCUREMENT_STRONG):
            log(f"  跳过(采购单): {title[:30]}")
            continue
        no_denial = strip_denial(full)
        item = {
            "id": iid, "title": title,
            "url": DETAIL_URL.format(iid=iid),
            "phones": phones,
            "scam": hit(no_denial, SCAM_WORDS),
            "good": hit(full, GOOD_REGION),
            "bad": hit(full, BAD_REGION),
            "factory": hit(full, FACTORY_WORDS),
        }
        matched.append(item)

    # 3) 排序：重点单在前（可外地优先；骗子沉底，不推）
    matched.sort(key=lambda it: (
        1 if it["scam"] else 0,
        1 if it["bad"] else 0,
        1 if it["factory"] and not it["good"] else 0,
        1 if it["factory"] else 0,
        0 if it["good"] else 1,
    ))
    pushable = [it for it in matched if not it["scam"]]
    log(f"命中 {len(matched)} 条，其中可推送 {len(pushable)} 条")

    # 4) 配额控制
    today = time.strftime("%Y-%m-%d")
    if state.get("push_date") != today:
        state["push_date"] = today
        state["push_count"] = 0
    remaining = DAILY_PUSH_LIMIT - int(state.get("push_count", 0))

    # 5) 推送
    to_push = pushable[:remaining] if remaining > 0 else []
    if to_push:
        lines = [f"160加工网新帖 {len(to_push)}条（{time.strftime('%m-%d %H:%M')}）"]
        for it in to_push:
            tags = []
            if it["good"]:
                tags.append("✅可发外地")
            if it["bad"]:
                tags.append("⚠️限当地")
            if it["factory"]:
                tags.append("⚠️找工厂/团队")
            tag_str = ("[" + " | ".join(tags) + "] ") if tags else ""
            phone = (" | 电话:" + " / ".join(it["phones"][:2])) if it["phones"] else ""
            lines.append(f"{tag_str}{it['title'][:44]}{phone}")
            lines.append(it["url"])
        desp = "\n\n".join(lines) if False else "\n".join(lines)
        if key:
            try:
                data = urllib.parse.urlencode({
                    "title": lines[0][:64], "desp": desp,
                }).encode()
                req = urllib.request.Request(
                    f"https://sctapi.ftqq.com/{key}.send", data=data, timeout=20)
                with urllib.request.urlopen(req) as resp:
                    result = resp.read().decode("utf-8", errors="replace")
                log(f"推送结果: {result[:200]}")
            except Exception as e:
                log(f"推送异常: {e}")
        else:
            log("无 SENDKEY，仅记录")
        state["push_count"] = int(state.get("push_count", 0)) + len(to_push)
        log(f"本次推送 {len(to_push)} 条")
    else:
        log(f"配额已用 {state.get('push_count',0)}/{DAILY_PUSH_LIMIT}，今日不再推送")

    # 6) 记录已见 + 保存状态（workflow 会把它提交回仓库）
    state["seen"] = sorted(seen)
    save_state(state)
    log("完成")


if __name__ == "__main__":
    main()
