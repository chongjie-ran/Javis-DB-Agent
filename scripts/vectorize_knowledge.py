#!/usr/bin/env python3
"""知识库向量化脚本 - 将alert_rules和SOP向量化到Chroma"""
import sys
import os

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.vector_store import VectorStore, _load_alert_rules, _load_sops


def main():
    print("=" * 60)
    print("zCloud 知识库向量化")
    print("=" * 60)

    # 创建向量存储
    vs = VectorStore(
        persist_dir="data/chroma_db",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",  # 可选：指定embedding模型
    )

    # 加载知识
    print("\n[1/3] 加载知识文件...")
    rules = _load_alert_rules("knowledge/alert_rules.yaml")
    sops = _load_sops("knowledge/sop")
    print(f"  - 告警规则: {len(rules)} 条")
    for r in rules:
        print(f"    • {r.title} ({r.id})")
    print(f"  - SOP文档: {len(sops)} 个")
    for s in sops:
        print(f"    • {s.title}")

    # 向量化
    print("\n[2/3] 向量化中（首次需要下载embedding模型，请耐心等待）...")
    result = vs.load_knowledge(force_reload=True)
    print(f"  结果: {result}")

    # 验证
    print("\n[3/3] 验证知识库...")
    stats = vs.get_stats()
    print(f"  - 告警规则向量数: {stats['alert_rules_count']}")
    print(f"  - SOP向量数: {stats['sops_count']}")
    print(f"  - Embedding模型: {stats['embedding_model']}")
    print(f"  - 存储路径: {stats['persist_dir']}")

    # 测试语义搜索
    print("\n[测试] 语义搜索测试...")
    test_queries = [
        "锁等待超时死锁",
        "CPU使用率过高",
        "主从复制延迟",
        "磁盘空间不足",
        "连接数打满",
    ]
    for q in test_queries:
        rules_found = vs.semantic_search_rules(q, top_k=3)
        print(f"\n  查询「{q}」:")
        for r in rules_found:
            print(f"    → {r['metadata'].get('alert_type', r['id'])} (距离: {r['distance']:.4f})")

    print("\n" + "=" * 60)
    print("知识库向量化完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
