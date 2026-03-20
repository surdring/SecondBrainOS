type HealthResponse = {
  status: string
}

async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch('/health')
  if (!res.ok) {
    throw new Error(`Health request failed: ${res.status}`)
  }
  const data: unknown = await res.json()
  if (typeof data !== 'object' || data === null || !('status' in data)) {
    throw new Error('Invalid health response')
  }
  const status = (data as { status: unknown }).status
  if (typeof status !== 'string') {
    throw new Error('Invalid health response')
  }
  return { status }
}

export default function App(): JSX.Element {
  return (
    <div className="p-4 font-sans">
      <h1 className="m-0 text-xl font-semibold">SecondBrainOS</h1>
      <p className="mt-2 text-sm text-gray-700">
        Web 项目已初始化。后端健康检查示例请在联调阶段通过反向代理或使用完整 baseUrl。
      </p>
      <button
        type="button"
        className="mt-3 rounded bg-gray-900 px-3 py-2 text-sm text-white hover:bg-gray-800"
        onClick={() => {
          fetchHealth()
            .then((r) => {
              console.log(r)
            })
            .catch((e: unknown) => {
              console.error(e)
            })
        }}
      >
        Test /health (console)
      </button>
    </div>
  )
}
