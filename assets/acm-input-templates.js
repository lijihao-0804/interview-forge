/* The standalone ACM editor uses the same input and output in both languages. */
(function (root) {
  'use strict';

  function javaProgram(body) {
    return 'import java.util.*;\n\npublic class Main {\n' +
      '    public static void main(String[] args) {\n        Scanner sc = new Scanner(System.in);\n' +
      body.split('\n').map(function (line) { return '        ' + line; }).join('\n') + '\n    }\n}\n';
  }

  var templates = {
    single: {
      title: '单个整数',
      prompt: '读入一个整数，原样输出。',
      codes: {
        python: 'n = int(input())\nprint(n)\n',
        java: javaProgram('long n = sc.nextLong();\nSystem.out.println(n);')
      },
      samples: [
        { name: '正整数', input: '42', expected: '42' },
        { name: '负整数', input: '-17', expected: '-17' },
        { name: '零', input: '0', expected: '0' }
      ]
    },
    two: {
      title: '两个整数求和',
      prompt: '同一行给出两个整数，输出它们的和。',
      codes: {
        python: 'a, b = map(int, input().split())\nprint(a + b)\n',
        java: javaProgram('long a = sc.nextLong();\nlong b = sc.nextLong();\nSystem.out.println(a + b);')
      },
      samples: [
        { name: '一正一负', input: '-7 2', expected: '-5' },
        { name: '和为零', input: '5   -5', expected: '0' },
        { name: '超过 32 位的和', input: '2000000000 2000000000', expected: '4000000000' }
      ]
    },
    array: {
      title: '数组求和',
      prompt: '先读个数 n，再读 n 个可跨行的整数。输出总和，空数组输出 0。',
      codes: {
        python: `import sys

values = iter(map(int, sys.stdin.buffer.read().split()))
n = next(values)
print(sum(next(values) for _ in range(n)))
`,
        java: javaProgram(`int n = sc.nextInt();
long sum = 0;
for (int i = 0; i < n; i++) {
    sum += sc.nextLong();
}
System.out.println(sum);`)
      },
      samples: [
        { name: '含负数的数组', input: '5\n3 -2 7 0 4', expected: '12' },
        { name: '整数分布在多行', input: '4\n10  20\n-30\t5', expected: '5' },
        { name: '空数组', input: '0', expected: '0' }
      ]
    },
    matrix: {
      title: '矩阵逐行求和',
      prompt: '先读行数和列数，再按行读入矩阵中的整数。每行输出一个行和。',
      codes: {
        python: `import sys

values = iter(map(int, sys.stdin.buffer.read().split()))
rows, cols = next(values), next(values)
for _ in range(rows):
    print(sum(next(values) for _ in range(cols)))
`,
        java: javaProgram(`int rows = sc.nextInt();
int cols = sc.nextInt();
for (int r = 0; r < rows; r++) {
    long sum = 0;
    for (int c = 0; c < cols; c++) {
        sum += sc.nextLong();
    }
    System.out.println(sum);
}`)
      },
      samples: [
        { name: '两行三列', input: '2 3\n1 2 3\n4 5 6', expected: '6\n15' },
        { name: '单列含负数', input: '3 1\n7\n0\n-4', expected: '7\n0\n-4' },
        { name: '只有一个元素', input: '1 1\n-9', expected: '-9' }
      ]
    },
    multi: {
      title: 'T 组数据',
      prompt: '先读组数 T，每组给出两个整数。逐行输出各组的和，T 为 0 时不输出。',
      codes: {
        python: `import sys

values = iter(map(int, sys.stdin.buffer.read().split()))
groups = next(values)
for _ in range(groups):
    print(next(values) + next(values))
`,
        java: javaProgram(`int groups = sc.nextInt();
for (int i = 0; i < groups; i++) {
    long a = sc.nextLong();
    long b = sc.nextLong();
    System.out.println(a + b);
}`)
      },
      samples: [
        { name: '三组独立求和', input: '3\n1 2\n-5 5\n4 -9', expected: '3\n0\n-5' },
        { name: '仅一组', input: '1\n12 30', expected: '42' },
        { name: '零组，无输出', input: '0', expected: '' }
      ]
    },
    eof: {
      title: '读到 EOF',
      prompt: '连续读整数直到 EOF，每两个数输出一行和。整数可跨行，也可以完全没有输入。',
      codes: {
        python: `import sys

values = iter(map(int, sys.stdin.buffer.read().split()))
for a in values:
    b = next(values)
    print(a + b)
`,
        java: javaProgram(`while (sc.hasNextLong()) {
    long a = sc.nextLong();
    long b = sc.nextLong();
    System.out.println(a + b);
}`)
      },
      samples: [
        { name: '多对整数', input: '1 2\n4 -7\n5 5', expected: '3\n-3\n10' },
        { name: '跨行配对、含空行', input: '10\n\n-3  8\n1', expected: '7\n9' },
        { name: '空输入', input: '', expected: '' }
      ]
    },
    string: {
      title: '读取整行字符串',
      prompt: '读一整行文本，在两侧各添一个竖线后输出。保留文本原有的空格。',
      codes: {
        python: 'line = input()\nprint("|" + line + "|")\n',
        java: javaProgram('String line = sc.nextLine();\nSystem.out.println("|" + line + "|");')
      },
      samples: [
        { name: '句中有空格', input: 'hello ACM world', expected: '|hello ACM world|' },
        { name: '行首和行尾有空格', input: '  a b  \n', expected: '|  a b  |' },
        { name: '空行', input: '\n', expected: '||' }
      ]
    },
    graph: {
      title: '图的邻接表',
      prompt: '先读点数 n 和边数 m，再读 m 条无向边。点从 1 编号，按编号输出各点的度数，以空格分隔。',
      codes: {
        python: `n, m = map(int, input().split())
neighbors = [[] for _ in range(n)]
for _ in range(m):
    u, v = map(int, input().split())
    neighbors[u - 1].append(v)
    neighbors[v - 1].append(u)
print(*(len(row) for row in neighbors))
`,
        java: javaProgram(`int n = sc.nextInt();
int m = sc.nextInt();
List<List<Integer>> neighbors = new ArrayList<>();
for (int i = 0; i < n; i++) {
    neighbors.add(new ArrayList<>());
}
for (int i = 0; i < m; i++) {
    int u = sc.nextInt();
    int v = sc.nextInt();
    neighbors.get(u - 1).add(v);
    neighbors.get(v - 1).add(u);
}
StringJoiner degrees = new StringJoiner(" ");
for (List<Integer> row : neighbors) {
    degrees.add(String.valueOf(row.size()));
}
System.out.println(degrees);`)
      },
      samples: [
        { name: '含孤立点', input: '5 3\n1 2\n2 3\n2 4', expected: '1 3 1 1 0' },
        { name: '单点无边', input: '1 0', expected: '0' },
        { name: '三点成环', input: '3 3\n1 2\n2 3\n3 1', expected: '2 2 2' }
      ]
    }
  };

  if (typeof module === 'object' && module.exports) module.exports = templates;
  else root.InterviewForgeAcmTemplates = templates;
})(typeof window !== 'undefined' ? window : globalThis);
