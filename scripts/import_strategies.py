#!/usr/bin/env python3
"""
策略导入脚本
一键导入预置的10个常见策略

Usage:
    python scripts/import_strategies.py
    python scripts/import_strategies.py --clear  # 先清空现有策略
"""

import argparse
import json
import sys
from pathlib import Path

import requests

API_BASE_URL = "http://localhost:18000"


def load_strategies():
    """加载策略模板"""
    template_file = Path(__file__).parent.parent / "docs" / "strategy-templates.json"
    with open(template_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["strategies"]


def check_api():
    """检查 API 是否可用"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/health", timeout=5)
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        return False


def list_strategies():
    """获取现有策略列表"""
    try:
        response = requests.get(f"{API_BASE_URL}/api/strategies")
        if response.status_code == 200:
            return response.json().get("items", [])
        return []
    except:
        return []


def delete_strategy(strategy_id):
    """删除策略"""
    try:
        response = requests.delete(f"{API_BASE_URL}/api/strategies/{strategy_id}")
        return response.status_code == 200
    except:
        return False


def create_strategy(strategy_data):
    """创建策略"""
    # 处理 config_json
    if "config_json" in strategy_data and isinstance(strategy_data["config_json"], dict):
        strategy_data["config_json"] = json.dumps(strategy_data["config_json"])
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/strategies",
            json=strategy_data
        )
        return response.status_code == 201, response.json()
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="导入预置策略")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="导入前清空现有策略",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="API 基础地址 (默认: http://localhost:8000)",
    )
    
    args = parser.parse_args()
    
    global API_BASE_URL
    API_BASE_URL = args.api_url
    
    print("=" * 60)
    print("AutoTrade 策略导入工具")
    print("=" * 60)
    
    # 检查 API
    print("\n[1/4] 检查 API 连接...")
    if not check_api():
        print("❌ 无法连接到后端服务")
        print(f"   请确保服务已启动: python start.py")
        print(f"   或使用 --api-url 指定其他地址")
        sys.exit(1)
    print("✅ API 连接正常")
    
    # 清空现有策略
    if args.clear:
        print("\n[2/4] 清空现有策略...")
        existing = list_strategies()
        for s in existing:
            delete_strategy(s["id"])
            print(f"   已删除: {s['name']}")
        print(f"✅ 已清空 {len(existing)} 个策略")
    
    # 加载策略模板
    print("\n[3/4] 加载策略模板...")
    strategies = load_strategies()
    print(f"✅ 加载了 {len(strategies)} 个策略")
    
    # 导入策略
    print("\n[4/4] 导入策略...")
    success_count = 0
    fail_count = 0
    
    for i, strategy in enumerate(strategies, 1):
        name = strategy["name"]
        print(f"\n   {i}. {name}...", end=" ")
        
        success, result = create_strategy(strategy)
        if success:
            print("✅")
            success_count += 1
        else:
            print(f"❌ ({result})")
            fail_count += 1
    
    # 总结
    print("\n" + "=" * 60)
    print("导入完成!")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")
    print("=" * 60)
    
    print(f"\n访问 http://localhost:3000/strategies 查看导入的策略")


if __name__ == "__main__":
    main()
