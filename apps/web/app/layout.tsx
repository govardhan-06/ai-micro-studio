import "./globals.css";

export const metadata = {
  title: "AI Micro-Story Studio",
  description: "A local studio for cinematic micro-fiction.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
