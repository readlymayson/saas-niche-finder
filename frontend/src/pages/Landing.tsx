import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"

export function Landing() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-8 p-8 text-center">
      <div className="max-w-xl space-y-4">
        <h1 className="text-4xl font-semibold tracking-tight">SaaS Niche Finder</h1>
        <p className="text-muted-foreground">
          B2B-ниши по русскоязычным сообществам: Telegram, VC.ru и Яндекс.Вордстат. Скоринг без
          западных рейтингов — под инди-хакеров и PM в РФ.
        </p>
        <div className="flex gap-3 justify-center flex-wrap">
          <Button asChild>
            <Link to="/login">Войти</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to="/register">Регистрация</Link>
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">Free — 5 карточек ниш в сутки · Pro — без лимита</p>
      </div>
    </div>
  )
}
