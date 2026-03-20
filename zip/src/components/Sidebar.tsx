import React from 'react';
import { LogOut, Brain, User, Calendar, Star, Info } from 'lucide-react';
import { auth, logout } from '../firebase';
import { Memory } from '../services/ai';
import { format } from 'date-fns';

interface SidebarProps {
  memories: Memory[];
}

export function Sidebar({ memories }: SidebarProps) {
  const user = auth.currentUser;

  const getIcon = (type: string) => {
    switch (type) {
      case 'preference': return <Star className="w-4 h-4 text-yellow-500" />;
      case 'event': return <Calendar className="w-4 h-4 text-blue-500" />;
      case 'fact': return <Info className="w-4 h-4 text-emerald-500" />;
      default: return <Brain className="w-4 h-4 text-zinc-500" />;
    }
  };

  return (
    <div className="w-72 bg-zinc-50 border-r border-zinc-200 flex flex-col h-screen text-zinc-800">
      <div className="p-4 border-b border-zinc-200 flex items-center gap-3 bg-white">
        <div className="w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center text-indigo-600">
          <Brain className="w-6 h-6" />
        </div>
        <div>
          <h1 className="font-semibold tracking-tight text-zinc-900">第二大脑 OS</h1>
          <p className="text-xs text-zinc-500">智能记忆系统</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-4">
          已提取的记忆 ({memories.length})
        </h2>

        {memories.length === 0 ? (
          <div className="text-center py-8 text-zinc-500 text-sm">
            <Brain className="w-8 h-8 mx-auto mb-3 opacity-20" />
            <p>暂无记忆。</p>
            <p className="text-xs mt-1">与我聊天来构建您的专属画像。</p>
          </div>
        ) : (
          <div className="space-y-3">
            {memories.map((memory) => (
              <div key={memory.id} className="bg-white border border-zinc-200 shadow-sm rounded-lg p-3 text-sm">
                <div className="flex items-start gap-2">
                  <div className="mt-0.5">{getIcon(memory.type)}</div>
                  <div>
                    <p className="text-zinc-700 leading-snug">{memory.content}</p>
                    {memory.timestamp && (
                      <p className="text-[10px] text-zinc-400 mt-1.5">
                        {memory.timestamp.toDate ? format(memory.timestamp.toDate(), 'yyyy-MM-dd HH:mm') : '刚刚'}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="p-4 border-t border-zinc-200 bg-zinc-50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 overflow-hidden">
            {user?.photoURL ? (
              <img src={user.photoURL} alt="User" className="w-8 h-8 rounded-full border border-zinc-200" referrerPolicy="no-referrer" />
            ) : (
              <div className="w-8 h-8 rounded-full bg-zinc-200 flex items-center justify-center">
                <User className="w-4 h-4 text-zinc-500" />
              </div>
            )}
            <div className="truncate">
              <p className="text-sm font-medium text-zinc-900 truncate">{user?.displayName || '用户'}</p>
              <p className="text-xs text-zinc-500 truncate">{user?.email}</p>
            </div>
          </div>
          <button
            onClick={logout}
            className="p-2 text-zinc-400 hover:text-zinc-700 hover:bg-zinc-200 rounded-lg transition-colors"
            title="退出登录"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
