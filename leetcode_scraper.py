import json
import requests
import re

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

LANG_MAP = {
    "cpp": {"lang": "cpp", "label": "C++", "langSlug": "cpp"},
    "csharp": {"lang": "csharp", "label": "C#", "langSlug": "csharp"},
    "python3": {"lang": "python", "label": "Python", "langSlug": "python3"},
}

DIFFICULTY_MAP = {
    "Easy": "easy",
    "Medium": "medium",
    "Hard": "hard",
}

HOT_100_SLUGS = [
    "two-sum",
    "add-two-numbers",
    "longest-substring-without-repeating-characters",
    "median-of-two-sorted-arrays",
    "longest-palindromic-substring",
    "zigzag-conversion",
    "reverse-integer",
    "string-to-integer-atoi",
    "palindrome-number",
    "regular-expression-matching",
    "container-with-most-water",
    "integer-to-roman",
    "roman-to-integer",
    "longest-common-prefix",
    "3sum",
    "3sum-closest",
    "letter-combinations-of-a-phone-number",
    "4sum",
    "remove-nth-node-from-end-of-list",
    "intersection-of-two-linked-lists",
    "valid-parentheses",
    "merge-two-sorted-lists",
    "merge-k-sorted-lists",
    "swap-nodes-in-pairs",
    "reverse-nodes-in-k-group",
    "remove-duplicates-from-sorted-array",
    "remove-element",
    "implement-strstr",
    "divide-two-integers",
    "powx-n",
    "substring-with-concatenation-of-all-words",
    "next-permutation",
    "search-in-rotated-sorted-array",
    "search-in-rotated-sorted-array-ii",
    "find-first-and-last-position-of-element-in-sorted-array",
    "search-insert-position",
    "valid-sudoku",
    "sudoku-solver",
    "merge-intervals",
    "insert-interval",
    "minimum-window-substring",
    "longest-repeating-character-replacement",
    "find-all-anagrams-in-a-string",
    "permutation-in-string",
    "binary-tree-inorder-traversal",
    "binary-tree-preorder-traversal",
    "binary-tree-postorder-traversal",
    "maximum-depth-of-binary-tree",
    "balanced-binary-tree",
    "binary-tree-level-order-traversal",
    "binary-tree-zigzag-level-order-traversal",
    "construct-binary-tree-from-preorder-and-inorder-traversal",
    "construct-binary-tree-from-inorder-and-postorder-traversal",
    "populating-next-right-pointers-in-each-node",
    "symmetric-tree",
    "maximum-path-sum",
    "path-sum",
    "unique-binary-search-trees",
    "validate-binary-search-tree",
    "invert-binary-tree",
    "serialize-and-deserialize-binary-tree",
    "clone-graph",
    "course-schedule",
    "course-schedule-ii",
    "number-of-islands",
    "surrounded-regions",
    "word-ladder",
    "jump-game",
    "jump-game-ii",
    "gas-station",
    "candy",
    "maximum-subarray",
    "maximum-product-subarray",
    "house-robber",
    "house-robber-ii",
    "house-robber-iii",
    "best-time-to-buy-and-sell-stock",
    "best-time-to-buy-and-sell-stock-ii",
    "best-time-to-buy-and-sell-stock-iii",
    "longest-increasing-subsequence",
    "coin-change",
    "combination-sum",
    "combination-sum-ii",
    "combination-sum-iii",
    "combination-sum-iv",
    "target-sum",
    "partition-equal-subset-sum",
    "longest-common-subsequence",
    "longest-palindromic-subsequence",
    "interleaving-string",
    "distinct-subsequences",
    "edit-distance",
    "triangle",
    "minimum-path-sum",
    "unique-paths",
    "unique-paths-ii",
    "climbing-stairs",
    "decode-ways",
    "kth-largest-element-in-an-array",
    "top-k-frequent-elements",
    "find-median-from-data-stream",
    "sliding-window-maximum",
    "largest-rectangle-in-histogram",
    "maximal-rectangle",
    "trapping-rain-water",
    "single-number",
    "single-number-ii",
    "single-number-iii",
    "majority-element",
    "set-matrix-zeroes",
    "rotate-image",
    "spiral-matrix",
    "search-a-2d-matrix",
    "search-a-2d-matrix-ii",
    "merge-sorted-array",
    "count-primes",
    "ugly-number",
    "ugly-number-ii",
    "happy-number",
    "reverse-bits",
    "number-of-1-bits",
    "bitwise-and-of-numbers-range",
    "subsets",
    "subsets-ii",
    "permutations",
    "permutations-ii",
    "combinations",
    "generate-parentheses",
    "palindrome-partitioning",
    "restore-ip-addresses",
    "word-search",
    "n-queens",
    "n-queens-ii",
]

UNIQUE_SLUGS = list(dict.fromkeys(HOT_100_SLUGS))


def get_problem_details(slug, session):
    query = """
    query questionData($titleSlug: String!) {
        question(titleSlug: $titleSlug) {
            title
            titleSlug
            difficulty
            content
            codeSnippets {
                lang
                langSlug
                code
            }
            topicTags {
                name
                slug
            }
        }
    }
    """
    
    variables = {"titleSlug": slug}
    
    response = session.post(LEETCODE_GRAPHQL_URL, json={"query": query, "variables": variables})
    data = response.json()
    
    question = data.get("data", {}).get("question", {})
    if not question:
        return None
    
    code_snippets = {}
    for snippet in question.get("codeSnippets", []):
        lang_slug = snippet.get("langSlug")
        if lang_slug in LANG_MAP:
            code_snippets[lang_slug] = snippet.get("code")
    
    tags = [tag.get("name") for tag in question.get("topicTags", [])]
    
    return {
        "title": question.get("title", ""),
        "difficulty": DIFFICULTY_MAP.get(question.get("difficulty"), "medium"),
        "description": question.get("content", ""),
        "code_snippets": code_snippets,
        "tags": tags
    }


def extract_examples(html_content):
    """Extract Input/Output/Explanation examples from LeetCode HTML content."""
    examples = []
    
    # Find all <pre> blocks that contain Input:/Output:
    pre_blocks = re.findall(r'<pre[^>]*>(.*?)</pre>', html_content, re.DOTALL)
    
    for block in pre_blocks:
        # Clean HTML tags but preserve structure
        text = re.sub(r'<strong>(.*?)</strong>', r'\1', block)
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&#39;', "'")
        text = text.replace('&quot;', '"')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&amp;', '&')
        text = re.sub(r'\n+', '\n', text).strip()
        
        if 'Input:' in text and 'Output:' in text:
            # Extract Input line
            input_match = re.search(r'Input:\s*(.*?)(?:\n|$)', text)
            output_match = re.search(r'Output:\s*(.*?)(?:\n|$)', text)
            explanation_match = re.search(r'Explanation:\s*(.*?)(?:\n-|\n\n|$)', text, re.DOTALL)
            
            if input_match and output_match:
                inp = input_match.group(1).strip()
                out = output_match.group(1).strip()
                example = {
                    "input": inp,
                    "expected": out
                }
                if explanation_match:
                    explanation = explanation_match.group(1).strip()
                    explanation = re.sub(r'\n+', ' ', explanation)
                    example["explanation"] = explanation
                examples.append(example)
    
    return examples


def clean_description(html_content):
    """Clean HTML content, keep examples in description."""
    # Replace <pre> blocks with markdown code blocks to preserve examples
    def replace_pre(match):
        content = match.group(1)
        # Clean inner tags
        text = re.sub(r'<strong>(.*?)</strong>', r'\1', content)
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&#39;', "'")
        text = text.replace('&quot;', '"')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&amp;', '&')
        text = text.strip()
        return f'\n```\n{text}\n```\n'
    
    text = re.sub(r'<pre[^>]*>(.*?)</pre>', replace_pre, html_content, flags=re.DOTALL)
    
    # Clean remaining HTML
    text = re.sub(r'<[^>]+>', '\n', text)
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&#39;', "'")
    text = text.replace('&quot;', '"')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&amp;', '&')
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = text.strip()
    
    return text


def guess_skill_tag(tags, title):
    tag_mapping = {
        "Hash Table": "数据结构/哈希表",
        "Linked List": "数据结构/链表",
        "Tree": "数据结构/树",
        "Binary Tree": "数据结构/树",
        "Binary Search": "算法/二分查找",
        "Dynamic Programming": "算法/动态规划",
        "Stack": "数据结构/栈",
        "Queue": "数据结构/队列",
        "Heap": "数据结构/堆",
        "Sorting": "算法/排序",
        "Graph": "算法/图论",
        "Backtracking": "算法/回溯",
        "Greedy": "算法/贪心",
        "Array": "数据结构/数组",
        "String": "算法/字符串",
        "Two Pointers": "算法/双指针",
        "Recursion": "算法/递归",
        "Sliding Window": "算法/滑动窗口",
        "Divide and Conquer": "算法/分治",
        "Trie": "数据结构/字典树",
        "Union Find": "算法/并查集",
        "BFS": "算法/图论",
        "DFS": "算法/图论",
        "Bit Manipulation": "算法/位运算",
        "Math": "算法/数学",
        "Design": "编程/设计",
    }
    
    title_lower = title.lower()
    for tag in tags:
        if tag in tag_mapping:
            return tag_mapping[tag]
    
    if "two sum" in title_lower:
        return "数据结构/哈希表"
    if "linked list" in title_lower:
        return "数据结构/链表"
    if "binary search" in title_lower:
        return "算法/二分查找"
    if "tree" in title_lower:
        return "数据结构/树"
    if "dp" in title_lower or "dynamic programming" in title_lower:
        return "算法/动态规划"
    
    return "算法/综合"


def main():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://leetcode.com/problemset/hot-100/"
    })
    
    print(f"Total unique slugs: {len(UNIQUE_SLUGS)}")
    
    drills = []
    for i, slug in enumerate(UNIQUE_SLUGS, 1):
        print(f"\nProcessing {i}/{len(UNIQUE_SLUGS)}: {slug}")
        
        try:
            details = get_problem_details(slug, session)
            if not details:
                print("  ERROR: No details found")
                continue
            
            html_content = details["description"]
            description = clean_description(html_content)
            test_cases = extract_examples(html_content)
            tags = details["tags"]
            title = details["title"]
            
            for lang_key, lang_info in LANG_MAP.items():
                if lang_key in details["code_snippets"]:
                    template = details["code_snippets"][lang_key]
                    skill_tag = guess_skill_tag(tags, title)
                    
                    drill = {
                        "id": f"lc_{slug}_{lang_key}",
                        "lang": lang_info["lang"],
                        "title": title,
                        "difficulty": details["difficulty"],
                        "description": description,
                        "template": template,
                        "test_cases": test_cases,
                        "skill_tag": skill_tag,
                    }
                    drills.append(drill)
                    print(f"  {lang_info['label']}: OK (examples: {len(test_cases)})")
                else:
                    print(f"  {lang_info['label']}: NOT FOUND")
                    
        except Exception as e:
            print(f"  Error: {e}")
    
    output = {
        "version": 1,
        "drills": drills
    }
    
    output_path = "C:\\Users\\24951\\Documents\\Codex\\2026-06-30\\z\\outputs\\companion_ai\\code_drills.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\nSaved {len(drills)} drills to {output_path}")


if __name__ == "__main__":
    main()
