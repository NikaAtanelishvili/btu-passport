// FE-10: the home page is the public Verify page; `/` stays as an alias for old links.
import { redirect } from "next/navigation";

export default function HomePage() {
  redirect("/verify");
}
