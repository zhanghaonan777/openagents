'use client';

import Image from 'next/image';
import { PanelLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useLayout } from './layout-context';
import { ProjectSwitcher } from '@/components/projects/project-switcher';

export function SidebarHeader() {
  const { sidebarToggle, isSidebarOpen } = useLayout();

  if (!isSidebarOpen) {
    return (
      <div className="flex items-center justify-center shrink-0 px-2.5 py-3.5">
        <Button mode="icon" variant="ghost" onClick={sidebarToggle} className="hidden lg:inline-flex shrink-0" title="Toggle sidebar">
          <PanelLeft />
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 shrink-0 px-3 py-3.5">
      <div className="size-8 shrink-0">
        <Image src="/logo-black.png" alt="OpenAgents" width={32} height={32} className="size-full object-contain dark:hidden" />
        <Image src="/logo-white.png" alt="OpenAgents" width={32} height={32} className="size-full object-contain hidden dark:block" />
      </div>
      {/* Top-level entity is the Project (org shows as the switcher subtitle). */}
      <ProjectSwitcher />
    </div>
  );
}
