# Missing frontend packages

Manually compared against the existing root `package.json`. None were installed, downloaded, or added to either package manifest.

| Approved package absent from package.json | Purpose | Expected API |
| --- | --- | --- |
| `tailwindcss` | Primary styling system and CSS utilities | Tailwind CSS 4 (`@import "tailwindcss"`, `@theme`, `@apply`) |
| `@tailwindcss/vite` | Tailwind Vite integration | Matching Tailwind CSS 4 plugin |
| `react-router-dom` | Navigation, route protection, post-sign-in redirects | React Router 7 declarative APIs |
| `lucide-react` | Interface icons | React-compatible Lucide exports |

React, React DOM, Vite, and `@vitejs/plugin-react` already appear in the manifest.

`vite.config.js` is prepared to import `@tailwindcss/vite`. The frontend cannot be built or started successfully until the missing dependencies are supplied. Installation and all executable validation are left to the project owner, as requested.
