"""Node definitions supplied by the judge, outside submitted solutions."""


class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


class Node:
    def __init__(self, val=0, next=None, random=None):
        self.val = val
        self.next = next
        self.random = random


def judge_namespace():
    return {"ListNode": ListNode, "TreeNode": TreeNode, "Node": Node}
