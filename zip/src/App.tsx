import React, { useEffect, useState } from 'react';
import { auth, db, loginWithGoogle } from './firebase';
import { onAuthStateChanged } from 'firebase/auth';
import { collection, query, orderBy, onSnapshot, addDoc, serverTimestamp, doc, setDoc, deleteDoc, updateDoc } from 'firebase/firestore';
import { Brain, Loader2 } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { Chat } from './components/Chat';
import { ErrorBoundary } from './components/ErrorBoundary';
import { chatWithMemory, extractMemories, Memory, Message } from './services/ai';

function AppContent() {
  const [user, setUser] = useState(auth.currentUser);
  const [isAuthReady, setIsAuthReady] = useState(false);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (currentUser) => {
      setUser(currentUser);
      setIsAuthReady(true);
      
      // Create a default conversation ID for MVP
      if (currentUser && !conversationId) {
        setConversationId('default-chat');
      }
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (!user || !isAuthReady) return;

    // Listen to Memories
    const memoriesRef = collection(db, `users/${user.uid}/memories`);
    const qMemories = query(memoriesRef, orderBy('timestamp', 'desc'));
    
    const unsubMemories = onSnapshot(qMemories, (snapshot) => {
      const mems: Memory[] = [];
      snapshot.forEach((doc) => {
        mems.push({ id: doc.id, ...doc.data() } as Memory);
      });
      setMemories(mems);
    }, (error) => {
      console.error("Error fetching memories:", error);
    });

    // Listen to Messages
    if (conversationId) {
      const messagesRef = collection(db, `users/${user.uid}/conversations/${conversationId}/messages`);
      const qMessages = query(messagesRef, orderBy('timestamp', 'asc'));
      
      const unsubMessages = onSnapshot(qMessages, (snapshot) => {
        const msgs: Message[] = [];
        snapshot.forEach((doc) => {
          msgs.push({ id: doc.id, ...doc.data() } as Message);
        });
        setMessages(msgs);
      }, (error) => {
        console.error("Error fetching messages:", error);
      });

      return () => {
        unsubMemories();
        unsubMessages();
      };
    }

    return () => unsubMemories();
  }, [user, isAuthReady, conversationId]);

  const handleSendMessage = async (content: string) => {
    if (!user || !conversationId) return;

    setIsLoading(true);
    try {
      // 1. Save User Message
      const messagesRef = collection(db, `users/${user.uid}/conversations/${conversationId}/messages`);
      await addDoc(messagesRef, {
        role: 'user',
        content,
        timestamp: serverTimestamp()
      });

      // 2. Get AI Response
      const aiResponseText = await chatWithMemory(content, memories, messages);

      // 3. Save AI Message
      await addDoc(messagesRef, {
        role: 'assistant',
        content: aiResponseText,
        timestamp: serverTimestamp()
      });

      // 4. Background: Extract Memories
      extractMemories(content, memories).then(async (operations) => {
        if (operations.length === 0) return;
        
        const memoriesRef = collection(db, `users/${user.uid}/memories`);
        
        for (const op of operations) {
          try {
            if (op.action === 'add' && op.content && op.type) {
              await addDoc(memoriesRef, {
                content: op.content,
                type: op.type,
                timestamp: serverTimestamp()
              });
            } else if (op.action === 'update' && op.memoryId && op.content && op.type) {
              const memDoc = doc(db, `users/${user.uid}/memories/${op.memoryId}`);
              await updateDoc(memDoc, {
                content: op.content,
                type: op.type,
                timestamp: serverTimestamp()
              });
            } else if (op.action === 'delete' && op.memoryId) {
              const memDoc = doc(db, `users/${user.uid}/memories/${op.memoryId}`);
              await deleteDoc(memDoc);
            }
          } catch (err) {
            console.error("Failed to apply memory operation:", op, err);
          }
        }
      });

    } catch (error) {
      console.error("Error sending message:", error);
    } finally {
      setIsLoading(false);
    }
  };

  if (!isAuthReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 text-zinc-800">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 text-zinc-800 p-4">
        <div className="max-w-md w-full bg-white border border-zinc-200 rounded-2xl p-8 text-center shadow-xl">
          <div className="w-16 h-16 bg-indigo-100 text-indigo-600 rounded-2xl flex items-center justify-center mx-auto mb-6">
            <Brain className="w-8 h-8" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight mb-2 text-zinc-900">第二大脑 OS</h1>
          <p className="text-zinc-500 mb-8 text-sm">
            您的个性化、具备上下文感知的数字记忆助手。登录以开始构建您的第二大脑。
          </p>
          <button
            onClick={loginWithGoogle}
            className="w-full py-3 px-4 bg-white border border-zinc-200 text-zinc-700 hover:bg-zinc-50 font-medium rounded-xl transition-colors flex items-center justify-center gap-2 shadow-sm"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            使用 Google 账号继续
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-white overflow-hidden">
      <Sidebar memories={memories} />
      <Chat 
        messages={messages} 
        onSendMessage={handleSendMessage} 
        isLoading={isLoading} 
      />
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AppContent />
    </ErrorBoundary>
  );
}
