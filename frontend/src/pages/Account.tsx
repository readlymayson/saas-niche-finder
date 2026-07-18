import { useState } from "react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { createPayment } from "@/lib/api"

export function Account() {
  const email = localStorage.getItem("user_email") ?? "—"
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const onPay = async () => {
    setError(null)
    setMessage(null)
    setLoading(true)
    try {
      const res = await createPayment()
      if (res.human_gate_required) {
        setMessage(res.message ?? "Оплата в режиме заглушки (настройте ЮKassa в .env)")
        if (res.confirmation_url) window.open(res.confirmation_url, "_blank")
      } else {
        window.location.href = res.confirmation_url
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка оплаты")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen p-8 max-w-lg mx-auto space-y-6">
      <Button variant="outline" asChild>
        <Link to="/dashboard">← Дашборд</Link>
      </Button>
      <h1 className="text-2xl font-semibold">Личный кабинет</h1>
      <dl className="text-sm space-y-2">
        <div>
          <dt className="text-muted-foreground">Email</dt>
          <dd>{email}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Тариф</dt>
          <dd>Free (5 просмотров/сутки) или Pro после оплаты</dd>
        </div>
      </dl>
      <Button onClick={() => void onPay()} disabled={loading}>
        {loading ? "…" : "Оформить Pro — 990 ₽/мес"}
      </Button>
      {message && <p className="text-sm text-muted-foreground">{message}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}
