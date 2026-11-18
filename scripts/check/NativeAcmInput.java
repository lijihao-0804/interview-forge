import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import judge.Hot200Judge;

/** Standard-input adapter for the published LeetCode methods. Expects one JSON value per line. */
class NativeAcmInput extends Hot200Judge {
    static List<Object> readArguments() throws Exception {
        var reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        List<Object> args = new ArrayList<>();
        for (String line; (line = reader.readLine()) != null; ) {
            if (!line.isBlank()) args.add(new Json(line).parse());
        }
        return args;
    }

    // JDK 17 has no bundled JSON library. Handle the catalog's JSON strings, numbers and containers.
    static final class Json {
        final String text;
        int offset;
        Json(String text) { this.text = text; }

        void spaces() {
            while (offset < text.length() && Character.isWhitespace(text.charAt(offset))) offset++;
        }
        boolean take(char token) {
            spaces();
            if (offset == text.length() || text.charAt(offset) != token) return false;
            offset++;
            return true;
        }
        void require(char token) {
            if (!take(token)) throw new IllegalArgumentException("Expected " + token + " at " + offset);
        }
        Object parse() {
            Object result = value();
            spaces();
            if (offset != text.length()) throw new IllegalArgumentException("Trailing JSON characters");
            return result;
        }
        Object value() {
            spaces();
            if (take('[')) {
                List<Object> list = new ArrayList<>();
                if (!take(']')) {
                    do { list.add(value()); } while (take(','));
                    require(']');
                }
                return list;
            }
            if (take('{')) {
                Map<String, Object> fields = new HashMap<>();
                if (!take('}')) {
                    do {
                        require('"');
                        String key = stringBody();
                        require(':');
                        fields.put(key, value());
                    } while (take(','));
                    require('}');
                }
                return fields;
            }
            if (take('"')) return stringBody();
            int start = offset;
            while (offset < text.length() && ",]} \t\r\n".indexOf(text.charAt(offset)) < 0) offset++;
            String literal = text.substring(start, offset);
            return switch (literal) {
                case "null" -> null;
                case "true" -> true;
                case "false" -> false;
                default -> {
                    if (literal.matches("-?(0|[1-9][0-9]*)")) yield Long.valueOf(literal);
                    yield Double.valueOf(literal);
                }
            };
        }
        String stringBody() {
            StringBuilder result = new StringBuilder();
            while (true) {
                char c = text.charAt(offset++);
                if (c == '"') return result.toString();
                if (c == '\\') {
                    c = switch (text.charAt(offset++)) {
                        case '"' -> '"'; case '\\' -> '\\'; case '/' -> '/';
                        case 'b' -> '\b'; case 'f' -> '\f'; case 'n' -> '\n';
                        case 'r' -> '\r'; case 't' -> '\t';
                        case 'u' -> {
                            int value = Integer.parseInt(text.substring(offset, offset + 4), 16);
                            offset += 4;
                            yield (char) value;
                        }
                        default -> throw new IllegalArgumentException("Invalid JSON escape");
                    };
                }
                result.append(c);
            }
        }
    }

    static int integer(Object value) { return ((Number) value).intValue(); }
    static int[] ints(Object value) { return (int[]) convert(value, int[].class); }
    static TreeNode binaryTree(Object value) {
        return tree((Integer[]) convert(value, Integer[].class));
    }
    static Node naryTree(Object value) {
        if (value == null) return null;
        List<?> pair = (List<?>) value;
        List<Node> children = new ArrayList<>();
        for (Object child : (List<?>) pair.get(1)) children.add(naryTree(child));
        return new Node(integer(pair.get(0)), children);
    }
    static NestedInteger nested(Object value) {
        if (value instanceof Number) return new NestedInteger(integer(value), null);
        List<NestedInteger> items = new ArrayList<>();
        for (Object child : (List<?>) value) items.add(nested(child));
        return new NestedInteger(null, items);
    }
    static Object convert(Object value, Type type) {
        if (value == null) return null;
        if (type instanceof ParameterizedType parameterized && parameterized.getRawType() == List.class) {
            List<Object> converted = new ArrayList<>();
            for (Object item : (List<?>) value) converted.add(convert(item, parameterized.getActualTypeArguments()[0]));
            return converted;
        }
        Class<?> cls = (Class<?>) type;
        if (cls.isInstance(value)) return value;
        if (cls == int.class || cls == Integer.class) return value instanceof Boolean b ? (b ? 1 : 0) : integer(value);
        if (cls == double.class) return ((Number) value).doubleValue();
        if (cls == char.class) return ((String) value).charAt(0);
        if (cls == char[].class && value instanceof String s) return s.toCharArray();
        if (cls.isArray()) {
            List<?> items = (List<?>) value;
            Object array = Array.newInstance(cls.getComponentType(), items.size());
            for (int i = 0; i < items.size(); i++) Array.set(array, i, convert(items.get(i), cls.getComponentType()));
            return array;
        }
        if (cls == TreeNode.class) return binaryTree(value);
        if (cls == ListNode.class) return list(ints(value));
        if (cls == Node.class) return naryTree(value);
        if (cls == NestedInteger.class) return nested(value);
        if (cls == Interval.class) {
            int[] pair = ints(value);
            return new Interval(pair[0], pair[1]);
        }
        throw new IllegalArgumentException("Unsupported input type: " + type);
    }
    static Object[] convertArgs(Executable fn, List<?> raw) {
        Type[] types = fn.getGenericParameterTypes();
        if (types.length != raw.size()) throw new IllegalArgumentException("Wrong argument count for " + fn);
        Object[] args = new Object[types.length];
        for (int i = 0; i < types.length; i++) args[i] = convert(raw.get(i), types[i]);
        return args;
    }
    static Object create(String name, List<?> raw) throws Exception {
        for (var constructor : Class.forName("Main$" + name).getDeclaredConstructors()) {
            if (constructor.getParameterCount() == raw.size()) return constructor.newInstance(convertArgs(constructor, raw));
        }
        throw new NoSuchMethodException(name);
    }
    static Method method(Object obj, String name) throws Exception {
        for (Method candidate : obj.getClass().getDeclaredMethods()) {
            if (candidate.getName().equals(name)) return candidate;
        }
        throw new NoSuchMethodException(name);
    }
    static Object call(Object obj, String name, List<?> raw) throws Exception {
        Method fn = method(obj, name);
        return fn.invoke(obj, convertArgs(fn, raw));
    }
    static ListNode prepend(Object raw, ListNode tail) {
        int[] values = ints(raw);
        for (int i = values.length - 1; i >= 0; i--) tail = new ListNode(values[i], tail);
        return tail;
    }
    static TreeNode findNode(TreeNode root, int value) {
        if (root == null || root.val == value) return root;
        TreeNode left = findNode(root.left, value);
        return left != null ? left : findNode(root.right, value);
    }
    static List<?> randomClone(Object obj, String name, List<?> input) throws Exception {
        Node[] nodes = new Node[input.size()];
        for (int i = 0; i < nodes.length; i++) nodes[i] = new Node(integer(((List<?>) input.get(i)).get(0)));
        for (int i = 0; i < nodes.length; i++) {
            Object index = ((List<?>) input.get(i)).get(1);
            nodes[i].random = index == null ? null : nodes[integer(index)];
            nodes[i].next = i + 1 < nodes.length ? nodes[i + 1] : null;
        }
        Node head = (Node) call(obj, name, Collections.singletonList(nodes.length == 0 ? null : nodes[0]));
        Map<Node, Integer> positions = new IdentityHashMap<>();
        for (Node n = head; n != null; n = n.next) positions.put(n, positions.size());
        List<Object> pairs = new ArrayList<>();
        for (Node n = head; n != null; n = n.next) pairs.add(Arrays.asList(n.val, positions.get(n.random)));
        return pairs;
    }
    static List<Object> design(int pid, String cls, String operation, List<Object> args) throws Exception {
        List<Object> out = new ArrayList<>();
        if (Set.of(146, 155, 208, 295).contains(pid)) {
            List<?> names = (List<?>) args.get(0);
            List<?> params = (List<?>) args.get(1);
            Object obj = create(cls, (List<?>) params.get(0));
            out.add(null);
            for (int i = 1; i < names.size(); i++) out.add(call(obj, (String) names.get(i), (List<?>) params.get(i)));
        } else if (pid == 281) {
            Object iterator = create(cls, args);
            while ((boolean) call(iterator, "hasNext", List.of())) out.add(call(iterator, "next", List.of()));
        } else {
            int end = args.size() - 1;
            Object obj = create(cls, args.subList(0, end));
            for (Object command : (List<?>) args.get(end)) {
                List<?> params = command instanceof List<?> values ? values : List.of(command);
                String name = operation;
                if (name.isEmpty()) {
                    name = (String) params.get(0);
                    params = params.subList(1, params.size());
                }
                Object value = call(obj, name, params);
                if (value != null) out.add(value);
            }
        }
        return out;
    }
    static Object codec(int pid, List<Object> args) throws Exception {
        Object obj = create("Codec", List.of());
        if (pid == 271) {
            Object encoded = call(obj, "encode", args);
            if (!call(obj, "decode", List.of(encoded)).equals(args.get(0))) throw new AssertionError("codec round trip");
            return encoded;
        }
        if (pid == 431) return levels((TreeNode) call(obj, "encode", args));
        String encoded = (String) call(obj, "serialize", args);
        Object decoded = call(obj, "deserialize", List.of(encoded));
        if (!encoded.equals(call(obj, "serialize", Collections.singletonList(decoded)))) throw new AssertionError("codec round trip");
        List<Object> result = new ArrayList<>();
        if (!encoded.isEmpty()) {
            String[] tokens = encoded.split(",");
            for (int i = 0; i < tokens.length; i += 2) result.add(List.of(Integer.valueOf(tokens[i]), Integer.valueOf(tokens[i + 1])));
        }
        return result;
    }
    @SuppressWarnings("unchecked")
    static Object solve(int pid, String cls, String operation, List<Object> args) throws Exception {
        if (cls.equals("Codec")) return codec(pid, args);
        if (!cls.equals("Solution")) return design(pid, cls, operation, args);
        Object obj = create(cls, List.of());
        Object first = args.get(0);
        Object second = args.size() > 1 ? args.get(1) : null;
        ListNode head = null;
        int nodeCount = 0;
        switch (pid) {
            case 138 -> { return randomClone(obj, operation, (List<?>) first); }
            case 141, 142 -> {
                head = list(ints(first));
                List<ListNode> nodes = new ArrayList<>();
                for (ListNode n = head; n != null; n = n.next) nodes.add(n);
                if (integer(second) >= 0) nodes.get(nodes.size() - 1).next = nodes.get(integer(second));
                nodeCount = nodes.size();
                args = Collections.singletonList(head);
            }
            case 160 -> {
                ListNode shared = list(ints(args.get(2)));
                args = Arrays.asList(prepend(first, shared), prepend(second, shared));
            }
            case 236, 285 -> {
                TreeNode root = binaryTree(first);
                args.set(0, root);
                for (int i = 1; i < args.size(); i++) args.set(i, findNode(root, integer(args.get(i))));
            }
            case 426 -> args.set(0, treeNode(binaryTree(first)));
            case 708 -> args.set(0, ring(ints(first)));
            case 1265 -> args.set(0, immutable(ints(first)));
            case 277 -> {
                Relation.matrix = (int[][]) convert(first, int[][].class);
                args.set(0, Relation.matrix.length);
            }
            case 1236 -> {
                Map<String, List<String>> graph = (Map<String, List<String>>) second;
                args.set(1, (HtmlParser) url -> graph.getOrDefault(url, List.of()));
            }
            case 1274 -> {
                int[][] ships = (int[][]) convert(first, int[][].class);
                args.set(0, (Sea) (hi, lo) -> Arrays.stream(ships).anyMatch(s ->
                    lo[0] <= s[0] && s[0] <= hi[0] && lo[1] <= s[1] && s[1] <= hi[1]));
            }
            case 702 -> {
                int[] values = ints(first);
                args.set(0, (ArrayReader) index -> index < values.length ? values[index] : Integer.MAX_VALUE);
            }
            case 489 -> args = List.of(new Robot((int[][]) convert(first, int[][].class), ints(second)));
            default -> { }
        }
        Method fn = method(obj, operation);
        Object[] params = convertArgs(fn, args);
        Object result = fn.invoke(obj, params);
        return switch (pid) {
            case 2, 19, 21, 23, 24, 25, 148, 206 -> result == null ? List.of() : result;
            case 31, 48, 73, 75, 189, 280, 283, 286 -> params[0];
            case 105, 108, 226 -> levels((TreeNode) result);
            case 114 -> levels((TreeNode) params[0]);
            case 142 -> {
                int index = -1;
                for (int i = 0; i < nodeCount; head = head.next, i++) {
                    if (head == result) { index = i; break; }
                }
                yield index;
            }
            case 160 -> result == null ? null : ((ListNode) result).val;
            case 236, 285 -> result == null ? null : ((TreeNode) result).val;
            case 186 -> new String((char[]) params[0]);
            case 426, 708 -> ringValues((Node) result, pid == 426);
            case 489 -> ((Robot) params[0]).cleaned;
            case 776 -> {
                TreeNode[] roots = (TreeNode[]) result;
                yield List.of(levels(roots[0]), levels(roots[1]));
            }
            case 1265 -> ImmutableListNode.printed;
            default -> result;
        };
    }
    static int compare(Object a, Object b) {
        if (a instanceof Number x && b instanceof Number y) return Double.compare(x.doubleValue(), y.doubleValue());
        if (a instanceof String x && b instanceof String y) return x.compareTo(y);
        List<?> left = (List<?>) a, right = (List<?>) b;
        for (int i = 0; i < Math.min(left.size(), right.size()); i++) {
            int cmp = compare(left.get(i), right.get(i));
            if (cmp != 0) return cmp;
        }
        return Integer.compare(left.size(), right.size());
    }
    static String output(int pid, Object result) {
        String raw = json(result);
        boolean inner = Set.of(15, 39, 49, 78, 249, 366).contains(pid);
        boolean outer = Set.of(1, 15, 17, 22, 39, 46, 49, 51, 78, 131, 247, 249, 254, 267, 272, 320, 347, 425, 438, 489, 1236).contains(pid);
        if (!inner && !outer) return raw;
        List<?> rows = (List<?>) new Json(raw).parse();
        if (inner) for (Object row : rows) ((List<?>) row).sort(NativeAcmInput::compare);
        if (outer) rows.sort(NativeAcmInput::compare);
        return json(rows);
    }
}
