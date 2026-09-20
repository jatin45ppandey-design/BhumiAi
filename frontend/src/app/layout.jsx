import './globals.css';
import './polish.css';
import './khatauni-review.css';
import './review-polish.css';

export const metadata = {
  title: 'BhumiAI',
  description: 'Land record digitization, verification, and traceable digital records.',
};

export default function Layout({ children }) {
  return <html lang="en"><body>{children}</body></html>;
}
