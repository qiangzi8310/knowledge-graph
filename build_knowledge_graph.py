#!/usr/bin/env python3
"""
民航知识库 - JSON 知识图谱构建脚本
从条款卡片提取：实体（条款）、关系（引用/层级/法规关联）
输出：knowledge_graph.json
"""
import os
import re
import json
from pathlib import Path
from collections import defaultdict

KB_BASE = Path("/mnt/d/clawdoc/民航知识库")
GRAPH_PATH = KB_BASE / "knowledge_graph.json"

# 法规目录配置
REGULATIONS = [
    {
        "id": "CCAR-121",
        "name": "大型飞机公共航空运输承运人运行合格审定规则",
        "version": "R8",
        "cards_dir": KB_BASE / "02_CCAR核心规章/CCAR-121大型运输航空/条款卡片",
        "color": "#2563EB"
    },
    {
        "id": "CCAR-145",
        "name": "民用航空器维修单位合格审定规定",
        "version": "R4",
        "cards_dir": KB_BASE / "02_CCAR核心规章/CCAR-145维修单位/条款卡片",
        "color": "#059669"
    },
    {
        "id": "CCAR-21",
        "name": "民用航空产品和零部件合格审定规定",
        "version": "R5",
        "cards_dir": KB_BASE / "02_CCAR核心规章/CCAR-21航空产品/条款卡片",
        "color": "#DC2626"
    },
    {
        "id": "CCAR-26",
        "name": "运输类飞机的持续适航和安全改进规定",
        "version": "R0",
        "cards_dir": KB_BASE / "02_CCAR核心规章/CCAR-26持续适航",
        "color": "#7C3AED"
    }
]

def parse_frontmatter(content: str) -> dict:
    """从卡片头部提取 YAML frontmatter"""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    fm_text = parts[1]
    fm = {}
    for line in fm_text.strip().split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm

def parse_card(content: str) -> dict:
    """解析单个条款卡片"""
    fm = parse_frontmatter(content)
    
    # 提取条款原文
    text_match = re.search(r"## 条款原文\s*\n(.*?)(?=## 关联条款|## 适用场景|## 合规要求红线|## 常见违规点|$)", content, re.DOTALL)
    clause_text = text_match.group(1).strip() if text_match else ""
    
    # 提取关联条款（已填的）
    ref_match = re.findall(r"\[\[(\d+\.\d+)\]\]", content)
    
    # 提取标签
    tag_match = re.findall(r"#(\w+)", fm.get("标签", ""))
    
    # 提取章节号
    chapter_match = re.search(r"第([A-ZA-Z0-9一二三四五六七八九十]+)章", fm.get("章节", ""))
    chapter = chapter_match.group(1) if chapter_match else "总则"
    
    # 条款号
    clause_num = fm.get("条款号", "")
    
    return {
        "frontmatter": fm,
        "clause_text": clause_text[:500],  # 保留前500字
        "references": ref_match,
        "tags": tag_match,
        "chapter": chapter,
        "clause_number": clause_num
    }

def build_node_id(regulation: str, clause_num: str) -> str:
    return f"{regulation.upper()}.{clause_num}"

def extract_text_references(text: str, regulation_id: str) -> list:
    """
    从条款正文中提取对其他条款的引用
    匹配模式：第X.Y条、第X.Z条、本章第X.Y条、本条(a)款等
    """
    refs = []
    
    # 匹配 121.X 条, CCAR-121.X条 等
    patterns = [
        rf"{regulation_id}\.(\d+)",
        rf"第(\d+)\.(\d+)条",
        rf"本章第(\d+)\.(\d+)条",
        rf"本条\((\w)\)款",
        rf"本规则第(\d+)\.(\d+)条",
    ]
    
    for p in patterns:
        for m in re.finditer(p, text):
            refs.append(m.group(0))
    
    # 去重
    return list(set(refs))

def extract_law_references(text: str) -> list:
    """从正文中提取对法律/法规的引用"""
    laws = []
    law_patterns = [
        r"《([^《》]+)》",
        r"依据《([^《》]+)》",
        r"根据《([^《》]+)》",
        r"按照《([^《》]+)》",
    ]
    for p in law_patterns:
        for m in re.finditer(p, text):
            laws.append(m.group(1))
    return list(set(laws))

def build_graph():
    """构建知识图谱"""
    nodes = []
    edges = []
    law_refs = defaultdict(list)  # 记录每个条款引用的法律
    
    for reg in REGULATIONS:
        cards_dir = reg["cards_dir"]
        if not cards_dir.exists():
            print(f"  跳过: {cards_dir} 不存在")
            continue
        
        # 判断是目录还是单文件（CCAR-26是PDF目录）
        if cards_dir.suffix == ".pdf":
            print(f"  跳过PDF: {cards_dir}")
            continue
        
        card_files = list(cards_dir.glob("*.md"))
        print(f"  处理 {reg['id']}: {len(card_files)} 个卡片")
        
        for card_path in card_files:
            try:
                content = card_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                print(f"    读取失败 {card_path.name}: {e}")
                continue
            
            card = parse_card(content)
            clause_num = card["clause_number"]
            if not clause_num:
                continue
            
            node_id = build_node_id(reg["id"], clause_num)
            
            # 从frontmatter提取标题
            title = clause_num
            if card["frontmatter"].get("条款号"):
                title = f"第{clause_num}条"
            
            # 提取关键词句（截取正文前200字）
            summary = card["clause_text"][:200].replace("\n", " ").strip()
            
            node = {
                "id": node_id,
                "type": "clause",
                "regulation": reg["id"],
                "regulation_name": reg["name"],
                "version": reg["version"],
                "clause_number": clause_num,
                "chapter": card["chapter"],
                "title": title,
                "summary": summary,
                "tags": card["tags"],
                "text_length": len(card["clause_text"]),
                "color": reg["color"]
            }
            nodes.append(node)
            
            # 关联条款边（从卡片里已填的关联条款）
            for ref in card["references"]:
                edges.append({
                    "source": node_id,
                    "target": f"{reg['id'].upper()}.{ref}",
                    "relation": "引用",
                    "source_reg": reg["id"]
                })
            
            # 从正文提取条款引用
            for ref_match in re.finditer(rf"{reg['id']}\.(\d+)", card["clause_text"]):
                ref_num = ref_match.group(1)
                target_id = f"{reg['id'].upper()}.{ref_num}"
                if target_id != node_id:
                    edges.append({
                        "source": node_id,
                        "target": target_id,
                        "relation": "正文引用",
                        "source_reg": reg["id"]
                    })
            
            # 法律引用
            for law in extract_law_references(card["clause_text"]):
                law_refs[node_id].append(law)
    
    # 构建图谱
    graph = {
        "metadata": {
            "generated": "2026-05-07",
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "regulations": [r["id"] for r in REGULATIONS],
            "source": "民航知识库条款卡片"
        },
        "nodes": nodes,
        "edges": edges,
        "law_references": {k: v for k, v in law_refs.items() if v}
    }
    
    return graph

def main():
    print("=" * 50)
    print("民航知识库 - JSON 图谱构建")
    print("=" * 50)
    
    graph = build_graph()
    
    # 去重边
    seen_edges = set()
    unique_edges = []
    for e in graph["edges"]:
        key = (e["source"], e["target"], e["relation"])
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)
    graph["edges"] = unique_edges
    
    # 统计
    print(f"\n构建完成:")
    print(f"  节点: {len(graph['nodes'])} 个条款")
    print(f"  边: {len(graph['edges'])} 条关系")
    print(f"  法律引用: {len(graph['law_references'])} 条")
    
    # 按法规统计节点
    reg_counts = defaultdict(int)
    for n in graph["nodes"]:
        reg_counts[n["regulation"]] += 1
    print(f"  分布: {dict(reg_counts)}")
    
    # 保存
    with open(GRAPH_PATH, 'w', encoding='utf-8') as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    print(f"\n已保存: {GRAPH_PATH}")
    
    # 打印样例
    if graph["nodes"]:
        print(f"\n节点示例:")
        for n in graph["nodes"][:3]:
            print(f"  {json.dumps(n, ensure_ascii=False)[:200]}")
    
    if graph["edges"]:
        print(f"\n边示例:")
        for e in graph["edges"][:3]:
            print(f"  {e['source']} --[{e['relation']}]--> {e['target']}")

if __name__ == "__main__":
    main()
