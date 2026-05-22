import { Sidebar } from './Sidebar';
import { Header } from './Header';

interface Props {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

export function AppLayout({ title, subtitle, children }: Props) {
  return (
    <div className="flex h-screen overflow-hidden bg-[#050607] relative">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 relative z-10">
        <Header title={title} subtitle={subtitle} />
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}