#!/usr/bin/env python3
"""
民航知识库 - 完整知识图谱构建 v2
包含：层级关系、跨规章引用、法律引用实体、CCAR-26节点
"""
import os, re, json
from pathlib import Path
from collections import defaultdict

KB_BASE = Path("/mnt/d/clawdoc/民航知识库")
VSTORE = KB_BASE / "vector_store.json"
GRAPH_PATH = KB_BASE / "knowledge_graph.json"

REGULATIONS = [
    {
        "id": "CCAR-121", "name": "大型飞机公共航空运输承运人运行合格审定规则",
        "version": "R8", "cards_dir": KB_BASE / "02_CCAR核心规章/CCAR-121大型运输航空/条款卡片",
        "color": "#2563EB", "prefix": "121"
    },
    {
        "id": "CCAR-145", "name": "民用航空器维修单位合格审定规定",
        "version": "R4", "cards_dir": KB_BASE / "02_CCAR核心规章/CCAR-145维修单位/条款卡片",
        "color": "#059669", "prefix": "145"
    },
    {
        "id": "CCAR-21", "name": "民用航空产品和零部件合格审定规定",
        "version": "R5", "cards_dir": KB_BASE / "02_CCAR核心规章/CCAR-21航空产品/条款卡片",
        "color": "#DC2626", "prefix": "21"
    },
    {
        "id": "CCAR-26", "name": "运输类飞机的持续适航和安全改进规定",
        "version": "R0", "cards_dir": None,  # PDF目录，用vector_store
        "color": "#7C3AED", "prefix": "26"
    }
]

# ============ 1. 解析条款卡片 ============
def parse_frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = {}
    for line in parts[1].strip().split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm

def parse_card(content: str) -> dict:
    fm = parse_frontmatter(content)
    text_match = re.search(r"## 条款原文\s*\n(.*?)(?=## 关联条款|## 适用场景|## 合规要求红线|## 常见违规点|$)", content, re.DOTALL)
    clause_text = text_match.group(1).strip() if text_match else ""
    ref_match = re.findall(r"\[\[(\d+\.\d+)\]\]", content)
    tag_match = re.findall(r"#(\w+)", fm.get("标签", ""))
    
    # 解析章节
    chapter_raw = fm.get("章节", "")
    chapter_match = re.search(r"第([A-Za-z0-9一二三四五六七八九十]+)章", chapter_raw)
    chapter = chapter_match.group(0) if chapter_match else "其他"
    sub_chapter = re.search(r"第([一二三四五六七八九十]+)节", chapter_raw)
    sub_section = sub_chapter.group(0) if sub_chapter else ""
    
    return {
        "frontmatter": fm,
        "clause_text": clause_text,
        "references": ref_match,
        "tags": tag_match,
        "chapter": chapter,
        "sub_section": sub_section,
        "clause_number": fm.get("条款号", ""),
        "title": fm.get("条款号", "").replace("121.", "第").replace("145.", "第").replace("21.", "第").replace("26.", "第") + "条"
    }

# ============ 2. 从向量库获取CCAR-26文本 ============
def get_ccar26_texts():
    """从vector_store获取CCAR-26的条款文本"""
    if not VSTORE.exists():
        return {}
    with open(VSTORE, 'r', encoding='utf-8') as f:
        store = json.load(f)
    texts = {}
    for k, v in store.items():
        if k.startswith("26C."):
            texts[k] = v.get("text", "")[:1000]
    return texts

# ============ 3. 提取条款号 ============
def extract_clause_refs(text: str, reg_id: str) -> list:
    """从正文中提取条款引用"""
    refs = []
    prefix = reg_id.replace("CCAR-", "")
    # 本规则/本章/本条 + 数字.X条
    patterns = [
        rf"本规则第{prefix}\.(\d+)\s*条",
        rf"本章第{prefix}\.(\d+)\s*条",
        rf"本条(?:第)?(\d+)\.(\d+)条",
        rf"第{prefix}\.(\d+)\s*条",
    ]
    for p in patterns:
        for m in re.finditer(p, text):
            refs.append(m.group(0))
    return list(set(refs))

# ============ 4. 法律引用 ============
KNOWN_LAWS = {
    "中华人民共和国民用航空法": {"id": "law:民用航空法", "type": "法律", "level": "上位法"},
    "中华人民共和国行政许可法": {"id": "law:行政许可法", "type": "法律", "level": "上位法"},
    "中华人民共和国行政处罚法": {"id": "law:行政处罚法", "type": "法律", "level": "上位法"},
    "中华人民共和国民法典": {"id": "law:民法典", "type": "法律", "level": "上位法"},
    "民用航空器适航管理条例": {"id": "law:适航管理条例", "type": "行政法规", "level": "行政法规"},
    "国务院对确需保留的行政审批项目设定行政许可的决定": {"id": "law:国务院决定", "type": "行政法规", "level": "行政法规"},
    "运输类飞机适航标准": {"id": "law:CCAR-25", "type": "规章", "level": "CCAR-25"},
    "民用航空器驾驶员合格审定规则": {"id": "law:CCAR-60", "type": "规章", "level": "CCAR-60"},
    "一般运行和飞行规则": {"id": "law:CCAR-91", "type": "规章", "level": "CCAR-91"},
    "国际民用航空公约": {"id": "law:ICAO公约", "type": "国际公约", "level": "国际"},
}

def extract_law_refs(text: str) -> list:
    found = []
    for law_name, law_info in KNOWN_LAWS.items():
        if law_name in text:
            found.append(law_info["id"])
    return found

def normalize_clause_num(reg_id: str, raw: str) -> str:
    """将条款引用字符串规范化为 标准ID"""
    m = re.search(r'(\d+)\.(\d+)', raw)
    if not m:
        return None
    num = m.group(1)
    sub = m.group(2)
    # 去掉重复前缀：如 121.121.1 -> 121.1
    if num == reg_id.replace("CCAR-", ""):
        return f"{reg_id}.{sub}"
    return f"{reg_id}.{num}.{sub}"

# ============ 5. 构建图谱 ============
def build_graph():
    nodes = []
    edges = []
    edge_set = set()
    law_nodes = {}  # id -> law node
    
    # --- 5a. 处理条款卡片 ---
    for reg in REGULATIONS:
        if reg["id"] == "CCAR-26":
            continue  # CCAR-26单独处理
        cards_dir = reg["cards_dir"]
        if not cards_dir or not cards_dir.exists():
            print(f"  跳过 {reg['id']}: 目录不存在")
            continue
        
        card_files = list(cards_dir.glob("*.md"))
        print(f"  {reg['id']}: {len(card_files)} 个卡片")
        
        for card_path in card_files:
            try:
                content = card_path.read_text(encoding="utf-8", errors="replace")
            except:
                continue
            
            card = parse_card(content)
            cn = card["clause_number"]
            if not cn:
                continue
            
            node_id = f"{reg['id']}.{cn}"
            
            # 标签去重
            tags = list(set(card["tags"]))
            
            node = {
                "id": node_id,
                "type": "clause",
                "regulation": reg["id"],
                "regulation_name": reg["name"],
                "version": reg["version"],
                "clause_number": cn,
                "chapter": card["chapter"],
                "sub_section": card["sub_section"],
                "title": card["title"],
                "summary": card["clause_text"][:300].replace("\n", " ").strip(),
                "tags": tags,
                "text_length": len(card["clause_text"]),
                "color": reg["color"]
            }
            nodes.append(node)
            
            # 关联条款边（卡片里手动填的）
            for ref in card["references"]:
                tgt = f"{reg['id']}.{ref}"
                key = (node_id, tgt, "引用")
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append({"source": node_id, "target": tgt, "relation": "引用", "source_reg": reg["id"]})
            
            # 正文引用
            for ref_str in extract_clause_refs(card["clause_text"], reg["id"]):
                tgt = normalize_clause_num(reg["id"], ref_str)
                if tgt and tgt != node_id:
                    key = (node_id, tgt, "正文引用")
                    if key not in edge_set:
                        edge_set.add(key)
                        edges.append({"source": node_id, "target": tgt, "relation": "正文引用", "source_reg": reg["id"]})
            
            # 法律引用 -> 创建法律节点 + 边
            for law_id in extract_law_refs(card["clause_text"]):
                if law_id not in law_nodes:
                    law_info = next((v for k, v in KNOWN_LAWS.items() if v["id"] == law_id), None)
                    if law_info:
                        law_nodes[law_id] = {
                            "id": law_id,
                            "type": law_info["type"],
                            "name": law_id.replace("law:", ""),
                            "level": law_info["level"],
                            "color": "#64748B"
                        }
                key = (node_id, law_id, "依据")
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append({"source": node_id, "target": law_id, "relation": "依据", "source_reg": reg["id"]})
    
    # --- 5b. 处理CCAR-26 (从向量库文本提取) ---
    print(f"  CCAR-26: 从向量库提取...")
    ccar26_texts = get_ccar26_texts()
    print(f"    获取到 {len(ccar26_texts)} 个文本块")
    
    ccar26_nodes = {}  # id -> node
    for key, text in ccar26_texts.items():
        # key格式: 26C.001.md -> 26.1
        m = re.search(r'26C\.(\d+)', key)
        if not m:
            continue
        seq = int(m.group(1))
        node_id = f"CCAR-26.{seq}"
        
        # 提取条款号
        clause_match = re.search(r'第26\.(\d+)\s*条', text)
        clause_num = clause_match.group(1) if clause_match else str(seq)
        
        # 章节判断
        chapter = "其他"
        if seq <= 3:
            chapter = "A章 总则"
        elif seq <= 10:
            chapter = "B章 结构和强度"
        
        node = {
            "id": node_id,
            "type": "clause",
            "regulation": "CCAR-26",
            "regulation_name": "运输类飞机的持续适航和安全改进规定",
            "version": "R0",
            "clause_number": f"26.{clause_num}",
            "chapter": chapter,
            "title": f"第26.{clause_num}条",
            "summary": text[:300].replace("\n", " ").strip(),
            "tags": ["CCAR-26", f"26.{clause_num}", "持续适航", "安全改进"],
            "text_length": len(text),
            "color": "#7C3AED"
        }
        ccar26_nodes[node_id] = node
        nodes.append(node)
        
        # CCAR-26对CCAR-25/CCAR-121的引用
        for other_reg in ["CCAR-25", "CCAR-121", "CCAR-21"]:
            for m in re.finditer(rf'{other_reg.replace("-","")}\.(\d+)', text):
                tgt = f"{other_reg}.{m.group(1)}"
                key = (node_id, tgt, "引用")
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append({"source": node_id, "target": tgt, "relation": "引用", "source_reg": "CCAR-26"})
        
        # 法律引用
        for law_id in extract_law_refs(text):
            if law_id not in law_nodes:
                law_info = next((v for k, v in KNOWN_LAWS.items() if v["id"] == law_id), None)
                if law_info:
                    law_nodes[law_id] = {
                        "id": law_id,
                        "type": law_info["type"],
                        "name": law_id.replace("law:", ""),
                        "level": law_info["level"],
                        "color": "#64748B"
                    }
            key = (node_id, law_id, "依据")
            if key not in edge_set:
                edge_set.add(key)
                edges.append({"source": node_id, "target": law_id, "relation": "依据", "source_reg": "CCAR-26"})
    
    # --- 5c. 层级关系边 ---
    print(f"  添加层级关系边...")
    # 按法规分组
    by_reg = defaultdict(list)
    for n in nodes:
        if n["type"] == "clause":
            by_reg[n["regulation"]].append(n)
    
    for reg_id, reg_nodes in by_reg.items():
        # 按章节分组
        chapters = defaultdict(list)
        for n in reg_nodes:
            ch = n.get("chapter", "其他")
            # 提取章编号
            ch_match = re.search(r'第([A-Za-z0-9]+)章', ch)
            ch_key = ch_match.group(1) if ch_match else ch
            chapters[ch_key].append(n)
        
        # 章节内按条款号排序
        for ch_key, clause_nodes in chapters.items():
            sorted_nodes = sorted(clause_nodes, key=lambda x: x["clause_number"])
            for i, n in enumerate(sorted_nodes):
                if i > 0:
                    prev = sorted_nodes[i-1]
                    key = (prev["id"], n["id"], "层级顺序")
                    if key not in edge_set:
                        edge_set.add(key)
                        edges.append({"source": prev["id"], "target": n["id"], "relation": "层级顺序", "source_reg": reg_id})
                
                # 章节 -> 条款
                ch_node_id = f"{reg_id}.ch-{ch_key}"
                if ch_node_id not in [nn["id"] for nn in nodes]:
                    ch_node = {
                        "id": ch_node_id,
                        "type": "chapter",
                        "regulation": reg_id,
                        "chapter": f"第{ch_key}章",
                        "title": f"第{ch_key}章",
                        "color": next((r["color"] for r in REGULATIONS if r["id"]==reg_id), "#64748B")
                    }
                    nodes.append(ch_node)
                key = (ch_node_id, n["id"], "包含")
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append({"source": ch_node_id, "target": n["id"], "relation": "包含", "source_reg": reg_id})
    
    # --- 5d. 跨规章引用 ---
    print(f"  添加跨规章引用边...")
    # CCAR-26 -> CCAR-25 (主要被引用关系)
    cross_refs = [
        ("CCAR-26", "CCAR-25", "引用"),
        ("CCAR-121", "CCAR-21", "引用"),
        ("CCAR-121", "CCAR-25", "引用"),
        ("CCAR-121", "CCAR-91", "引用"),
        ("CCAR-121", "CCAR-135", "引用"),
        ("CCAR-145", "CCAR-21", "引用"),
    ]
    for src_reg, tgt_reg, rel in cross_refs:
        key = (src_reg, tgt_reg, rel)
        if key not in edge_set:
            edge_set.add(key)
            edges.append({"source": src_reg, "target": tgt_reg, "relation": rel, "source_reg": src_reg})
            # 同时创建规章节点（如果没有的话）
            if not any(n["id"] == tgt_reg for n in nodes):
                reg_info = next((r for r in REGULATIONS if r["id"] == tgt_reg), None)
                color = reg_info["color"] if reg_info else "#64748B"
                nodes.append({
                    "id": tgt_reg,
                    "type": "regulation",
                    "regulation": tgt_reg,
                    "title": tgt_reg,
                    "color": color
                })
            if not any(n["id"] == src_reg for n in nodes):
                reg_info = next((r for r in REGULATIONS if r["id"] == src_reg), None)
                color = reg_info["color"] if reg_info else "#64748B"
                nodes.append({
                    "id": src_reg,
                    "type": "regulation",
                    "regulation": src_reg,
                    "title": src_reg,
                    "color": color
                })
    
    # 添加法律节点
    for law_node in law_nodes.values():
        if not any(n["id"] == law_node["id"] for n in nodes):
            nodes.append(law_node)
    
    return nodes, edges

def main():
    print("=" * 60)
    print("民航知识图谱 - 完整版 v2")
    print("=" * 60)
    
    nodes, edges = build_graph()
    
    # 统计
    node_types = defaultdict(int)
    for n in nodes:
        node_types[n["type"]] += 1
    
    rel_types = defaultdict(int)
    for e in edges:
        rel_types[e["relation"]] += 1
    
    reg_counts = defaultdict(int)
    for n in nodes:
        if n["type"] == "clause":
            reg_counts[n.get("regulation","")] += 1
    
    graph = {
        "metadata": {
            "generated": "2026-05-07",
            "version": "2.0",
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "node_types": dict(node_types),
            "relation_types": dict(rel_types),
            "clause_counts": dict(reg_counts),
            "source": "民航知识库条款卡片 + 向量库CCAR-26"
        },
        "nodes": nodes,
        "edges": edges
    }
    
    print(f"\n构建完成:")
    print(f"  节点: {len(nodes)} ({dict(node_types)})")
    print(f"  边: {len(edges)} ({dict(rel_types)})")
    print(f"  条款分布: {dict(reg_counts)}")
    
    with open(GRAPH_PATH, 'w', encoding='utf-8') as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    print(f"\n已保存: {GRAPH_PATH}")
    
    # 打印样例
    print(f"\n节点样例:")
    for n in nodes[:3]:
        print(f"  {n['id']} ({n['type']}) - {n.get('title','')[:40]}")
    print(f"\n边样例:")
    for e in edges[:5]:
        print(f"  {e['source']} --[{e['relation']}]--> {e['target']}")

if __name__ == "__main__":
    main()
