import * as React from "react";

import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "border-input/60 file:text-foreground placeholder:text-muted-foreground/70 selection:bg-primary/30 selection:text-primary-foreground flex h-10 w-full min-w-0 rounded-xl border bg-background/50 px-4 py-2 text-base shadow-sm transition-all duration-300 outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/20 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        "aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
