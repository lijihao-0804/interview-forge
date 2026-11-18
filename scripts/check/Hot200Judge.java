package judge;

import java.lang.reflect.Array;
import java.util.*;

/** Judge-supplied structures for compiling the Markdown's real Java examples. */
public class Hot200Judge {
    public static class TreeNode {
        public int val;
        public TreeNode left, right;
        public TreeNode(int value) { val = value; }
    }
    public static class Node {
        public int val;
        public Node left, right, next, random;
        public List<Node> children;
        public Node(int v) { val = v; }
        public Node(int v, Node n) { this(v); next = n; }
        public Node(int v, List<Node> c) { this(v); children = c; }
    }
    public static class ListNode {
        public int val;
        public ListNode next;
        public ListNode(int v) { val = v; }
        public ListNode(int v, ListNode n) { this(v); next = n; }
    }
    public static class Interval {
        public int start, end;
        public Interval(int s, int e) { start = s; end = e; }
    }
    public static class Relation {
        public static int[][] matrix;
        protected boolean knows(int a, int b) { return matrix[a][b] != 0; }
    }
    public interface HtmlParser { List<String> getUrls(String url); }
    public interface ArrayReader { int get(int index); }
    public interface Sea { boolean hasShips(int[] hi, int[] lo); }
    public record NestedInteger(Integer scalar, List<NestedInteger> items) {
        public boolean isInteger() { return scalar != null; }
        public Integer getInteger() { return scalar; }
        public List<NestedInteger> getList() { return items; }
    }
    public static class ImmutableListNode {
        int val;
        ImmutableListNode next;
        public static List<Integer> printed = new ArrayList<>();
        public ImmutableListNode getNext() { return next; }
        public void printValue() { printed.add(val); }
    }
    public static class Robot {
        final int[][] room;
        int r, c, d;
        public final Set<List<Integer>> cleaned = new HashSet<>();
        public Robot(int[][] room, int[] pos) { this.room=room; r=pos[0]; c=pos[1]; }
        public void turnRight() { d=(d+1)%4; }
        public void turnLeft() { d=(d+3)%4; }
        public void clean() { cleaned.add(List.of(r,c)); }
        public boolean move() {
            int y=r+new int[]{-1,0,1,0}[d], x=c+new int[]{0,1,0,-1}[d];
            if (y<0 || y>=room.length || x<0 || x>=room[y].length || room[y][x]==0) return false;
            r=y; c=x;
            return true;
        }
    }
    public static TreeNode tree(Integer... values) {
        if (values.length==0 || values[0]==null) return null;
        TreeNode root=new TreeNode(values[0]);
        Queue<TreeNode> q=new ArrayDeque<>();
        q.add(root);
        for (int i=1;i<values.length;) {
            TreeNode n=q.remove();
            if (values[i]!=null) q.add(n.left=new TreeNode(values[i]));
            i++;
            if(i<values.length && values[i]!=null) q.add(n.right=new TreeNode(values[i]));
            i++;
        }
        return root;
    }
    public static List<Integer> levels(TreeNode root) {
        List<Integer> vals=new ArrayList<>();
        Queue<TreeNode> q=new LinkedList<>();
        q.add(root);
        while (!q.isEmpty()) {
            TreeNode n=q.remove();
            vals.add(n==null?null:n.val);
            if(n!=null) { q.add(n.left); q.add(n.right); }
        }
        while(!vals.isEmpty() && vals.get(vals.size()-1)==null) vals.remove(vals.size()-1);
        return vals;
    }
    public static Node treeNode(TreeNode t) {
        if(t==null) return null;
        Node n=new Node(t.val);
        n.left=treeNode(t.left); n.right=treeNode(t.right);
        return n;
    }
    public static ListNode list(int... values) {
        ListNode head=null;
        for(int i=values.length-1;i>=0;i--) head=new ListNode(values[i],head);
        return head;
    }
    public static Node ring(int... values) {
        Node head=null, prev=null;
        for(int x:values) {
            Node n=new Node(x);
            if(prev!=null) prev.next=n; else head=n;
            prev=n;
        }
        if(prev!=null) prev.next=head;
        return head;
    }
    public static ImmutableListNode immutable(int... values) {
        ImmutableListNode head=null;
        for(int i=values.length-1;i>=0;i--) {
            ImmutableListNode n=new ImmutableListNode(); n.val=values[i]; n.next=head; head=n;
        }
        return head;
    }
    public static List<Integer> ringValues(Node head, boolean binary) {
        List<Integer> out=new ArrayList<>(); Node n=head;
        while(n!=null) {
            out.add(n.val); n=binary?n.right:n.next;
            if(n==head) break;
            if(out.size()>10000) throw new AssertionError("broken circular list");
        }
        return out;
    }
    static String quoted(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"', '\\' -> out.append('\\').append(c);
                case '\b' -> out.append("\\b");
                case '\f' -> out.append("\\f");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20 || Character.isSurrogate(c)) out.append(String.format("\\u%04x", (int)c));
                    else out.append(c);
                }
            }
        }
        return out.append('"').toString();
    }
    /** Emit one JSON result, preserving array order and all JSON string escapes. */
    public static String json(Object v) {
        if(v==null) return "null";
        if(v instanceof String s) return quoted(s);
        if(v instanceof Number || v instanceof Boolean) return v.toString();
        if(v instanceof Interval x) return json(List.of(x.start,x.end));
        if(v instanceof TreeNode t) return json(levels(t));
        if(v instanceof ListNode n) {
            List<Integer> vals=new ArrayList<>();
            while(n!=null) {vals.add(n.val);n=n.next;}
            return json(vals);
        }
        StringJoiner result=new StringJoiner(",","[","]");
        if(v instanceof Iterable<?> items) for(Object x:items) result.add(json(x));
        else if(v.getClass().isArray()) for(int i=0;i<Array.getLength(v);i++) result.add(json(Array.get(v,i)));
        else throw new IllegalArgumentException(v.getClass().getName());
        return result.toString();
    }
}
