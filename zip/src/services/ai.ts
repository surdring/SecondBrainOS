import { GoogleGenAI, Type } from '@google/genai';

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

export interface Memory {
  id: string;
  content: string;
  type: 'preference' | 'fact' | 'event';
  timestamp: any;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: any;
}

export async function chatWithMemory(
  userMessage: string,
  currentMemories: Memory[],
  chatHistory: Message[]
): Promise<string> {
  const memoryContext = currentMemories.length > 0
    ? `\n\n以下是你目前了解到的关于用户的记忆（Agentic Memory）：\n${currentMemories.map(m => `- [${m.type}] ${m.content}`).join('\n')}`
    : '\n\n你目前没有任何关于用户的记忆。';

  const systemInstruction = `你是一个个性化的 AI 助手（第二大脑 OS）。
你的目标是成为一个有用的、主动的、具备上下文感知的数字大脑。
你会记住关于用户的细节，并利用这些信息提供高度个性化的回答。
除非必要，不要明确说“根据我的记忆...”。只需结合上下文自然地回答即可。${memoryContext}`;

  const historyContents = chatHistory.map(msg => ({
    role: msg.role === 'assistant' ? 'model' : 'user',
    parts: [{ text: msg.content }]
  }));

  historyContents.push({ role: 'user', parts: [{ text: userMessage }] });

  try {
    const response = await ai.models.generateContent({
      model: 'gemini-3.1-pro-preview',
      contents: historyContents,
      config: {
        systemInstruction,
        temperature: 0.7,
      }
    });
    return response.text || "I'm sorry, I couldn't process that.";
  } catch (error) {
    console.error("Error generating chat response:", error);
    throw error;
  }
}

export interface MemoryOperation {
  action: 'add' | 'update' | 'delete';
  memoryId?: string; // Required for update/delete
  content?: string; // Required for add/update
  type?: 'preference' | 'fact' | 'event'; // Required for add/update
}

export async function extractMemories(
  userMessage: string,
  currentMemories: Memory[]
): Promise<MemoryOperation[]> {
  const memoryContext = currentMemories.length > 0
    ? `当前记忆：\n${currentMemories.map(m => `ID: ${m.id} | 类型: ${m.type} | 内容: ${m.content}`).join('\n')}`
    : '当前记忆：无';

  const prompt = `分析用户的消息，提取关于他们的新事实、偏好或事件。
将其与他们的“当前记忆”进行比较。
- 如果有新的事实/偏好/事件，请“add”（添加）它。
- 如果用户的消息与现有记忆矛盾或更新了现有记忆，请“update”（更新）它。
- 如果用户明确要求忘记某事，请“delete”（删除）它。
- 如果没有新信息，请返回一个空数组。

用户消息：“${userMessage}”

${memoryContext}

返回一个操作的 JSON 数组。`;

  try {
    const response = await ai.models.generateContent({
      model: 'gemini-3.1-pro-preview',
      contents: prompt,
      config: {
        responseMimeType: 'application/json',
        responseSchema: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              action: { type: Type.STRING, enum: ['add', 'update', 'delete'] },
              memoryId: { type: Type.STRING, description: 'ID of the memory to update or delete. Leave empty for add.' },
              content: { type: Type.STRING, description: 'The content of the memory. Required for add and update.' },
              type: { type: Type.STRING, enum: ['preference', 'fact', 'event'], description: 'Type of memory. Required for add and update.' }
            },
            required: ['action']
          }
        }
      }
    });

    const text = response.text;
    if (!text) return [];

    const operations: MemoryOperation[] = JSON.parse(text);
    return operations;
  } catch (error) {
    console.error("Error extracting memories:", error);
    return [];
  }
}
