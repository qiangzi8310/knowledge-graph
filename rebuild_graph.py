#!/usr/bin/env python3
"""
重建知识图谱 - v3最终版（修复单行frontmatter解析）
"""
import re, json
from pathlib import Path
from collections import defaultdict

KB = Path("/mnt/d/clawdoc/民航知识库")
VSTORE = KB / "vector_store.json"
GRAPH = KB / "knowledge_graph.json"

REG_DIRS = [
    ("CCAR-121", KB / "02_CCAR核心规章/CCAR-121大型运输航空/条款卡片", "#2563EB"),
    ("CCAR-145", KB / "02_CCAR核心规章/CCAR-145维修单位/条款卡片", "#059669"),
    ("CCAR-21",  KB / "02_CCAR核心规章/CCAR-21航空产品/条款卡片", "#DC2626"),
]

def parse_card(content):
    """解析单行frontmatter格式的条款卡片"""
    cn_match = re.search(r"条款号:\s*([^\s]+)", content)
    cn = cn_match.group(1) if cn_match else ""
    
    # frontmatter里的wikilinks（前1000字符）
    fm_refs = re.findall(r"\[\[(\d+\.\d+)\]\]", content[:1000])
    
    # 正文##关联条款section
    sec = re.search(r"## 关联条款\s*\n(.*?)(?=##|\Z)", content, re.DOTALL)
    sec_refs = re.findall(r"\[\[(\d+\.\d+)\]\]", sec.group(1) if sec else "")
    
    # 标签
    tags_match = re.search(r"标签:\s*([^\n]+)", content)
    tags = re.findall(r"#(\w+)", tags_match.group(1) if tags_match else "")
    
    # 章节
    ch_match = re.search(r"章节:\s*第([A-Za-z0-9]+)章", content)
    chapter = f"第{ch_match.group(1)}章" if ch_match else "其他"
    
    # 条款原文摘要
    tm = re.search(r"## 条款原文\s*\n(.*?)(?=## 关联条款|## 适用场景|$)", content, re.DOTALL)
    summary = tm.group(1)[:300].replace("\n", " ").strip() if tm else ""
    
    return {
        "clause_number": cn,
        "references": list(set(fm_refs + sec_refs)),
        "tags": list(set(tags)),
        "chapter": chapter,
        "summary": summary
    }

# ==================== 读取所有条款卡片 ====================
print("读取条款卡片...")
all_clauses = {}  # (reg, cn) -> node_data
for reg_id, cards_dir, color in REG_DIRS:
    md_files = list(cards_dir.glob("*.md"))
    print(f"  {reg_id}: {len(md_files)} 个卡片")
    for card_path in md_files:
        content = card_path.read_text(encoding="utf-8", errors="replace")
        card = parse_card(content)
        cn = card["clause_number"]
        if not cn:
            continue
        all_clauses[(reg_id, cn)] = {
            "reg": reg_id,
            "cn": cn,
            "references": card["references"],
            "chapter": card["chapter"],
            "tags": card["tags"],
            "summary": card["summary"],
            "color": color
        }

print(f"卡片条款合计: {len(all_clauses)}")

# ==================== CCAR-26从向量库 ====================
if VSTORE.exists():
    with open(VSTORE, 'r', encoding='utf-8') as f:
        vs = json.load(f)
    for k, v in vs.items():
        if k.startswith("26C."):
            seq = k.replace("26C.", "").replace(".md", "")
            cn = f"26.{seq}"
            all_clauses[("CCAR-26", cn)] = {
                "reg": "CCAR-26",
                "cn": cn,
                "references": [],
                "chapter": "其他",
                "tags": ["CCAR-26"],
                "summary": v.get("text", "")[:300],
                "color": "#7C3AED"
            }
print(f"含CCAR-26后: {len(all_clauses)} 个条款")

# ==================== 构建backlinks ====================
backlinks = defaultdict(set)
for (reg, cn), data in all_clauses.items():
    for ref in data["references"]:
        for (r2, c2) in all_clauses:
            if c2 == ref:
                backlinks[(r2, c2)].add((reg, cn))
                break

# ==================== 构建节点和边 ====================
nodes = []
edges = []
edge_set = set()

# 条款节点 + 引用边
for (reg, cn), data in all_clauses.items():
    node_id = f"{reg}.{cn}"
    node = {
        "id": node_id,
        "type": "clause",
        "regulation": reg,
        "clause_number": cn,
        "chapter": data["chapter"],
        "title": f"第{cn}条",
        "summary": data["summary"],
        "tags": data["tags"],
        "color": data["color"]
    }
    nodes.append(node)
    
    # 出边 - 引用（正向wikilink）
    for ref in data["references"]:
        tgt_id = f"{reg}.{ref}"
        key = (node_id, tgt_id, "引用")
        if key not in edge_set:
            edge_set.add(key)
            edges.append({"source": node_id, "target": tgt_id, "relation": "引用", "source_reg": reg})
    
    # 入边 - 被引用（反向wikilink from backlinks）
    for src_reg, src_cn in backlinks.get((reg, cn), set()):
        src_id = f"{src_reg}.{src_cn}"
        key = (src_id, node_id, "引用")
        if key not in edge_set:
            edge_set.add(key)
            edges.append({"source": src_id, "target": node_id, "relation": "引用", "source_reg": src_reg})

# 层级边 - 章节节点 + 包含/层级顺序
chapters_map = defaultdict(list)
for n in nodes:
    chapters_map[(n["regulation"], n["chapter"])].append(n)

for (reg, ch), clause_nodes in chapters_map.items():
    # 章节节点ID
    ch_key = ch.replace("第", "").replace("章", "").replace("总则", "Z")
    ch_node_id = f"{reg}.ch-{ch_key}"
    color = next(c[2] for c in REG_DIRS if c[0] == reg) if reg != "CCAR-26" else "#7C3AED"
    ch_node = {
        "id": ch_node_id,
        "type": "chapter",
        "regulation": reg,
        "chapter": ch,
        "title": ch,
        "color": color
    }
    if not any(n["id"] == ch_node_id for n in nodes):
        nodes.append(ch_node)
    
    # 排序 + 层级顺序
    sorted_clauses = sorted(clause_nodes, key=lambda x: x["clause_number"])
    prev = None
    for n in sorted_clauses:
        key = (ch_node_id, n["id"], "包含")
        if key not in edge_set:
            edge_set.add(key)
            edges.append({"source": ch_node_id, "target": n["id"], "relation": "包含", "source_reg": reg})
        if prev:
            k2 = (prev["id"], n["id"], "层级顺序")
            if k2 not in edge_set:
                edge_set.add(k2)
                edges.append({"source": prev["id"], "target": n["id"], "relation": "层级顺序", "source_reg": reg})
        prev = n

# 跨规章边
for src, tgt, rel in [("CCAR-121","CCAR-21","引用"),("CCAR-121","CCAR-25","引用"),
                        ("CCAR-121","CCAR-91","引用"),("CCAR-145","CCAR-21","引用"),
                        ("CCAR-26","CCAR-25","引用")]:
    k = (src, tgt, rel)
    if k not in edge_set:
        edge_set.add(k)
        edges.append({"source": src, "target": tgt, "relation": rel, "source_reg": src})

# ==================== 统计并保存 ====================
node_types = defaultdict(int)
for n in nodes:
    node_types[n["type"]] += 1

rel_types = defaultdict(int)
for e in edges:
    rel_types[e["relation"]] += 1

clause_counts = defaultdict(int)
for n in nodes:
    if n["type"] == "clause":
        clause_counts[n["regulation"]] += 1

graph = {
    "metadata": {
        "generated": "2026-05-07",
        "version": "3.0",
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "node_types": dict(node_types),
        "relation_types": dict(rel_types),
        "clause_counts": dict(clause_counts),
        "source": "条款卡片(修复解析) + 向量库CCAR-26"
    },
    "nodes": nodes,
    "edges": edges
}

with open(GRAPH, 'w', encoding='utf-8') as f:
    json.dump(graph, f, ensure_ascii=False, indent=2)

print(f"\n图谱 v3.0 构建完成:")
print(f"  节点: {len(nodes)} ({dict(node_types)})")
print(f"  边: {len(edges)} ({dict(rel_types)})")
print(f"  条款分布: {dict(clause_counts)}")
print(f"已保存: {GRAPH}")
