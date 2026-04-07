import { Button } from "@/components/ui/button"

function App() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
      <div className="max-w-lg text-center space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">SaaS Niche Finder</h1>
        <p className="text-muted-foreground">
          MVP: B2B-ниши по Telegram, VC.ru и Яндекс.Вордстат (РФ).
        </p>
      </div>
      <div className="flex gap-3">
        <Button>Войти</Button>
        <Button variant="outline">Регистрация</Button>
      </div>
    </div>
  )
}

export default App
