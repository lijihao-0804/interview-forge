/* Labels use server-issued fields; permissions are always enforced server-side. */
(function (root) {
  "use strict";
  function label(user) {
    if (!user) return "用户";
    if (user.role === "admin" && user.effective_role === "super_admin") return "超级管理员";
    return user.role === "admin" ? "管理员" : "用户";
  }
  root.InterviewForgeRoles = { label: label, isAdmin: function (user) { return !!user && user.role === "admin"; } };
})(typeof window !== "undefined" ? window : globalThis);
