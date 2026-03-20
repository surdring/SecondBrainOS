import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Bot, User } from 'lucide-react';
import { Message } from '../services/ai';
import ReactMarkdown from 'react-markdown';
import { format } from 'date-fns';
import { cn } from '../lib/utils';

interface ChatProps {
  messages: Message[];
  onSendMessage: (content: string) => void;
  isLoading: boolean;
}

export function Chat({ messages, onSendMessage, isLoading }: ChatProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSendMessage(input.trim());
    setInput('');
  };

  return (
    <div className="flex-1 flex flex-col h-screen bg-white">
      {/* Header */}
      <div className="h-16 border-b border-zinc-200 flex items-center px-6 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <h2 className="text-lg font-medium text-zinc-800">对话</h2>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-zinc-400 space-y-4">
            <Bot className="w-12 h-12 opacity-20" />
            <p className="text-center max-w-sm text-zinc-500">
              你好！我是你的第二大脑 OS。告诉我关于你自己、你的偏好或你正在做的事情，我会记住它们以便在未来的对话中帮助你。
            </p>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={cn(
                "flex gap-4 max-w-3xl mx-auto",
                msg.role === 'user' ? "flex-row-reverse" : "flex-row"
              )}
            >
              <div className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
                msg.role === 'user' ? "bg-zinc-100 border border-zinc-200" : "bg-indigo-100 text-indigo-600"
              )}>
                {msg.role === 'user' ? <User className="w-5 h-5 text-zinc-500" /> : <Bot className="w-5 h-5" />}
              </div>

              <div className={cn(
                "px-4 py-3 rounded-2xl max-w-[80%]",
                msg.role === 'user'
                  ? "bg-zinc-100 text-zinc-800 rounded-tr-sm border border-zinc-200"
                  : "bg-transparent text-zinc-800"
              )}>
                {msg.role === 'assistant' ? (
                  <div className="prose prose-sm max-w-none text-zinc-800">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                )}

                {msg.timestamp && (
                  <p className={cn(
                    "text-[10px] mt-2",
                    msg.role === 'user' ? "text-zinc-400 text-right" : "text-zinc-400"
                  )}>
                    {msg.timestamp.toDate ? format(msg.timestamp.toDate(), 'HH:mm') : '刚刚'}
                  </p>
                )}
              </div>
            </div>
          ))
        )}

        {isLoading && (
          <div className="flex gap-4 max-w-3xl mx-auto">
            <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
              <Bot className="w-5 h-5" />
            </div>
            <div className="px-4 py-3">
              <Loader2 className="w-5 h-5 text-zinc-400 animate-spin" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white border-t border-zinc-200">
        <div className="max-w-3xl mx-auto relative">
          <form onSubmit={handleSubmit} className="relative flex items-end gap-2 bg-zinc-50 border border-zinc-200 rounded-2xl p-2 focus-within:border-zinc-300 focus-within:ring-1 focus-within:ring-zinc-300 transition-all shadow-sm">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              placeholder="发送消息给第二大脑..."
              className="w-full max-h-32 min-h-[44px] bg-transparent text-zinc-800 placeholder:text-zinc-400 resize-none outline-none py-3 px-3 text-sm"
              rows={1}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="p-3 bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-200 disabled:text-zinc-400 text-white rounded-xl transition-colors shrink-0 mb-0.5"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
          <p className="text-center text-[10px] text-zinc-400 mt-2">
            AI 可能会犯错。请核实重要信息。
          </p>
        </div>
      </div>
    </div>
  );
}
