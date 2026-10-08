import type { Metadata } from "next";
export const metadata: Metadata = {title:"MistrFlow | Zakázky bez chaosu",description:"Přehledná správa zakázek a klientů pro řemeslníky."};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="cs"><body style={{margin:0,fontFamily:"Arial, sans-serif",background:"#0b1220",color:"#f8fafc"}}>{children}</body></html>}
