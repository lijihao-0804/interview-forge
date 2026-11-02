# 091 按路径替换二叉树

## 题目描述

将一颗子二叉树按照路径替换到另一棵根二叉树中，得到一颗新的二叉树。替换动作满足如下条件：

1. 同一节点，子二叉树和根二叉树同时存在，则取子二叉树的值。
2. 同一节点，子二叉树存在，根二叉树不存在，则取子二叉树的值。
3. 同一节点，子二叉树不存在，根二叉树存在，则取根二叉树的值。
4. 父节点处理完后，递归处理子节点，直至子二叉树和根二叉树都不存在子节点时退出。

## 输入描述

输入为三行

第一行：一个数组，表示根二叉树。二叉树的每个节点在1到9之间，包含1和9，空节点用0表示。

第二行：一个字符串，表示子二叉树根节点对应根二叉树的节点，如`/1/2`对应（每个节点下不存在相同的子节点，即`path`对应的子树最多只有一个）。

第三行：一个数组表示子二叉树，二叉树的每个节点在1到9之间，包含1和9，空节点用0表示。

**输入限制：**

1. 给定的根叉树和子叉树深度不超过5。
2. 给定的路径始终有效，并且会指向唯一的子二叉树，不存在子树不存在的场景。

## 输出描述

一个数组，表示一个二叉树，逐层从左到右描述，为空的节点忽略（与输入不同）。

## 示例描述

### 示例一

**输入：**
```text
[1,1,2,0,0,4,5]
/1/2
[5,3,0]
```

**输出：**
```text
[1,1,5,3]
```

### 示例二

**输入：**
```text
[1,1,2,0,0,4,5]
/1/1
[5,3,0]
```

**输出：**
```text
[1,5,2,3,4,5]
```

## 解题思路

1. 构建根二叉树和子二叉树。
2. 按照路径替换根二叉树，使用递归：
   - 确定方法和参数：方法`replace_tree`，参数：根二叉树`root_tree`、子二叉树`sub_tree`、路径`path`、路径下标`i`。
   - 终止条件：如果路径节点等于左节点的值，则并入左子树，如果路径节点等于右节点的值，则并入右子树。
   - 递归处理：如果路径节点等于左节点的值，则递归搜索左子树，如果路径节点等于右节点的值，则递归搜索右子树。
3. 使用广度优先搜索BFS，将根二叉树展开为数组。
4. 返回数组结果。

## 解题代码

```python
import itertools


class TreeNode:
    def __init__(self, val):
        self.val = val
        self.left = None
        self.right = None


def build_tree(nums, index):
    node = None
    if index < len(nums) and nums[index] != 0:
        node = TreeNode(nums[index])
        node.left = build_tree(nums, 2 * index + 1)
        node.right = build_tree(nums, 2 * index + 2)
    return node


def replace_tree(root_tree: TreeNode, sub_tree: TreeNode, path: list, i):
    if i == len(path) - 1:
        if root_tree.left and root_tree.left.val == path[i]:
            root_tree.left = sub_tree
            return
        elif root_tree.right and root_tree.right.val == path[i]:
            root_tree.right = sub_tree
            return

    if root_tree.left and root_tree.left.val == path[i]:
        replace_tree(root_tree.left, sub_tree, path, i + 1)
    elif root_tree.right and root_tree.right.val == path[i]:
        replace_tree(root_tree.right, sub_tree, path, i + 1)


def flatten_tree(node: TreeNode, level: int, node_nums):
    if len(node_nums) == level:
        node_nums.append([])

    node_nums[level].append(node.val)

    if node.left and node.left.val != 0:
        flatten_tree(node.left, level + 1, node_nums)
    if node.right and node.right.val != 0:
        flatten_tree(node.right, level + 1, node_nums)


def solve_method(root_tree_nums, subtree_path, sub_tree_nums):
    subtree_path = subtree_path[1:].split("/")
    subtree_path = [0 if x == "" else int(x) for x in subtree_path]

    # 构建根二叉树和子二叉树
    root_tree = build_tree(root_tree_nums, 0)
    sub_tree = build_tree(sub_tree_nums, 0)

    if len(sub_tree_nums) > 1:
        replace_tree(root_tree, sub_tree, subtree_path, 1)
    else:
        # 子二叉树不存在，根二叉树存在，则取根二叉树的值
        root_tree = sub_tree

    # 展开根二叉树为数组
    result = []
    flatten_tree(root_tree, 0, result)
    return list(itertools.chain(*result))


if __name__ == '__main__':
    root = [1, 1, 2, 0, 0, 4, 5]
    nodes = "/1/2"
    sub_tree = [5, 3, 0]
    assert solve_method(root, nodes, sub_tree) == [1, 1, 5, 3]

    root = [1, 1, 2, 0, 0, 4, 5]
    nodes = "/1/1"
    sub_tree = [5, 3, 0]
    assert solve_method(root, nodes, sub_tree) == [1, 5, 2, 3, 4, 5]
```