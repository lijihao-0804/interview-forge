// 婚礼策划AI - Logo
export function WeddingAILogo({
  className,
  width = 40,
  height = 40,
}: {
  width?: number;
  height?: number;
  className?: string;
}) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      {/* 拱门形状 */}
      <path
        d="M8 56V32C8 18.7452 18.7452 8 32 8C45.2548 8 56 18.7452 56 32V56"
        stroke="url(#gold-gradient)"
        strokeWidth="3.5"
        strokeLinecap="round"
        fill="none"
      />

      {/* AI字样的A与拱门融合 */}
      <path
        d="M24 48L32 28L40 48"
        stroke="url(#gold-gradient)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />

      {/* 拱门顶部的心形 */}
      <path
        d="M32 14C33.5 12.5 35.5 12 37 13C38.5 14 38.5 16 37 18L32 22L27 18C25.5 16 25.5 14 27 13C28.5 12 30.5 12.5 32 14Z"
        fill="url(#rose-gradient)"
      />

      {/* 两侧的小爱心 */}
      <circle cx="16" cy="20" r="2" fill="#F4C2C2" />
      <circle cx="48" cy="20" r="2" fill="#F4C2C2" />

      {/* 底部装饰 */}
      <path
        d="M20 56H44"
        stroke="url(#gold-gradient)"
        strokeWidth="2"
        strokeLinecap="round"
      />

      {/* 渐变定义 */}
      <defs>
        <linearGradient id="gold-gradient" x1="8" y1="8" x2="56" y2="56">
          <stop offset="0%" stopColor="#D4AF37" />
          <stop offset="50%" stopColor="#F0D78C" />
          <stop offset="100%" stopColor="#D4AF37" />
        </linearGradient>
        <linearGradient id="rose-gradient" x1="27" y1="13" x2="37" y2="22">
          <stop offset="0%" stopColor="#F4C2C2" />
          <stop offset="100%" stopColor="#FFB6C1" />
        </linearGradient>
      </defs>
    </svg>
  );
}

// 简化版本 - 用于侧边栏
export function WeddingAISimpleLogo({
  className,
  width = 32,
  height = 32,
}: {
  width?: number;
  height?: number;
  className?: string;
}) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      {/* 拱门 */}
      <path
        d="M6 34V20C6 11.7157 12.7157 5 21 5C29.2843 5 36 11.7157 36 20V34"
        stroke="url(#gold-gradient-small)"
        strokeWidth="2.5"
        strokeLinecap="round"
        fill="none"
      />
      {/* A字 */}
      <path
        d="M15 30L21 17L27 30"
        stroke="url(#gold-gradient-small)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      {/* 心形 */}
      <path
        d="M21 9C22 8 23.5 7.5 24.5 8C25.5 8.5 25.5 10 24.5 11.5L21 14L17.5 11.5C16.5 10 16.5 8.5 17.5 8C18.5 7.5 20 8 21 9Z"
        fill="#F4C2C2"
      />
      <defs>
        <linearGradient id="gold-gradient-small" x1="6" y1="5" x2="36" y2="34">
          <stop offset="0%" stopColor="#D4AF37" />
          <stop offset="50%" stopColor="#F0D78C" />
          <stop offset="100%" stopColor="#D4AF37" />
        </linearGradient>
      </defs>
    </svg>
  );
}