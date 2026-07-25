"use client";

import Image from "next/image";
import Link from "next/link";
import { Menu } from "lucide-react";
import type { PageKey } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { AlertsBell } from "@/components/shell/alerts-bell";
import { UserMenu } from "@/components/shell/user-menu";

/**
 * Slim system chrome: brand, alerts inbox, account. Page identity lives in
 * PageHeader; film filters live on the pages that use them.
 */
export function AppTopbar({
  activePage,
  onMenuClick,
}: {
  activePage: PageKey;
  onMenuClick: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-border-soft bg-[oklch(0.13_0.038_252/0.86)] px-3 backdrop-blur-md lg:px-5">
      <Button
        variant="ghost"
        size="icon"
        className="size-10 lg:hidden"
        onClick={onMenuClick}
        aria-label="Open navigation"
      >
        <Menu className="size-5" />
      </Button>

      <Link href="/" className="flex items-center" aria-label="Football IQ home">
        <Image
          src="/brand/toledo-rocket.png"
          width={184}
          height={52}
          alt="Toledo Football IQ"
          className="h-8 w-auto object-contain"
          priority
        />
      </Link>

      <div className="flex-1" />

      <AlertsBell active={activePage === "alerts"} />
      <UserMenu />
    </header>
  );
}
