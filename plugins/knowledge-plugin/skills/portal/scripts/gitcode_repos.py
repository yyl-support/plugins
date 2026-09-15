#!/usr/bin/env python3
"""列出 GitCode 组织下的全部仓库。

用法：
    python3 gitcode_repos.py <org>

需要环境变量 GITCODE_TOKEN。

为什么需要这个脚本：gitcode MCP 注册的 18 个工具全是"仓库内部"维度的
操作（issue / PR / 看板 / 里程碑），**没有"按组织枚举仓库"的接口**。
想知道团队在 GitCode 上有哪些仓，只能走这个 API。

只读，不写任何东西。
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.gitcode.com/api/v5"
PER_PAGE = 100
TIMEOUT = 30


def fetch_repos(org, token):
    """拉取组织下全部仓库。

    该 API 不返回分页头（实测无 Link / X-Total），只能靠"本页数量不足
    per_page"判断到底——所以不能用固定的页数上限，否则仓库变多会静默截断。
    """
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({"per_page": PER_PAGE, "page": page})
        url = f"{API}/orgs/{urllib.parse.quote(org)}/repos?{q}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                batch = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                sys.exit("✗ 认证失败（401）——GITCODE_TOKEN 无效或已过期。\n"
                         "  注意：gitcode MCP 也是在启动时校验 token，无效则整个 server 不启动。")
            if e.code == 404:
                sys.exit(f"✗ 组织不存在或无权访问：{org}")
            sys.exit(f"✗ HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            sys.exit(f"✗ 网络不可达：{e.reason}")
        except json.JSONDecodeError:
            sys.exit("✗ 响应不是 JSON——可能被网关拦截，检查网络或代理")

        if not batch:
            break
        out.extend(batch)
        if len(batch) < PER_PAGE:
            break
        page += 1
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    token = os.environ.get("GITCODE_TOKEN", "").strip()
    if not token:
        sys.exit("✗ 未设置 GITCODE_TOKEN 环境变量。\n"
                 "  token 向团队申请，设置后重运行即可。")

    org = sys.argv[1]
    repos = fetch_repos(org, token)
    if not repos:
        print(f"组织 {org} 下没有可见仓库（或当前账号无权访问其中任何仓库）。")
        return

    # 按最后推送时间降序——新人最关心"哪些还在动"
    repos.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)

    n_priv = sum(1 for r in repos if r.get("private"))
    print("=" * 74)
    print(f"组织：{org}    共 {len(repos)} 个仓库"
          f"（私有 {n_priv} / 公开 {len(repos) - n_priv}）")
    print("=" * 74)
    print()
    print(f"  {'最后推送':<12} {'仓库名':<34} {'可见':<5} 分支")
    for r in repos:
        name = r.get("name") or r.get("path") or "?"
        pushed = (r.get("pushed_at") or "")[:10] or "—"
        vis = "私有" if r.get("private") else "公开"
        branch = r.get("default_branch") or "—"
        print(f"  {pushed:<12} {name:<34} {vis:<5} {branch}")
        desc = (r.get("description") or "").strip()
        if desc:
            print(f"      {desc}")
    print()
    print(f"  完整地址前缀：https://gitcode.com/{org}/<仓库名>")
    print()
    print("  说明：只列出当前 token 有权看到的仓库。若某仓库对当前账号不可见，")
    print("        这里不会出现——列表为空不代表组织下没有仓库。")


if __name__ == "__main__":
    main()
