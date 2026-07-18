import { Link, useSearchParams } from "react-router-dom"

import { Button } from "@/components/ui/button"

export function BillingSuccess() {
  const [params] = useSearchParams()
  const paymentId = params.get("payment_id")
  const mode = params.get("mode")

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-2xl font-semibold">Оплата</h1>
      {mode === "stub" ? (
        <p className="text-muted-foreground text-sm max-w-md">
          Режим заглушки. После настройки ЮKassa и webhook подписка Pro активируется автоматически.
        </p>
      ) : (
        <p className="text-muted-foreground text-sm">
          Спасибо! Подписка активируется после подтверждения webhook.
        </p>
      )}
      {paymentId && <p className="text-xs text-muted-foreground">ID: {paymentId}</p>}
      <Button asChild>
        <Link to="/dashboard">В дашборд</Link>
      </Button>
    </div>
  )
}
