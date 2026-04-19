import React from 'react';

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <div className="flex h-screen bg-gray-100 font-sans">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r shadow-sm">
        <div className="p-4 border-b">
          <h1 className="text-xl font-bold text-gray-800">Friction Radar</h1>
        </div>
        <nav className="p-4 space-y-2">
          <a href="/" className="block p-2 rounded hover:bg-gray-50 text-gray-700">Dashboard</a>
          <a href="/companies" className="block p-2 rounded hover:bg-gray-50 text-gray-700">Companies</a>
          <a href="/collection" className="block p-2 rounded hover:bg-gray-50 text-gray-700">Collection Runs</a>
        </nav>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 overflow-auto p-8">
        {children}
      </main>
    </div>
  );
};
