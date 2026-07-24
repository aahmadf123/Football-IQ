"use client";

// Compatibility re-export: the shell was rebuilt in src/components/shell/
// (topbar + sidebar + mobile drawer; the old right rail is gone). Pages
// import FootballShell from here until each is migrated, then this stub goes.
export { FootballShell } from "@/components/shell/app-shell";
