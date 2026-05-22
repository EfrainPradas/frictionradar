import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { SidebarV2 } from './SidebarV2';
import { HeaderV2 } from './HeaderV2';

export function AppShellV2() {
  useEffect(() => {
    const prev = document.documentElement.getAttribute('data-theme');
    document.documentElement.setAttribute('data-theme', 'v2');
    return () => {
      if (prev) document.documentElement.setAttribute('data-theme', prev);
      else document.documentElement.removeAttribute('data-theme');
    };
  }, []);

  return (
    <div className="min-h-screen flex bg-fr-bg text-fr-ink">
      <SidebarV2 />
      <div className="flex flex-col flex-1 min-w-0">
        <HeaderV2 />
        <main className="flex-1 min-h-0 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
