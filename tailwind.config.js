/**
 * Source unique du design system.
 *
 * Avant, la configuration vivait en double dans deux objets JS inline
 * (base.html et login.html) qui avaient déjà divergé. Les couleurs pointent
 * ici des variables CSS définies dans static/src/app.css : le mode sombre est
 * une simple redéfinition de ces variables, pas une variante `dark:` à répéter
 * sur chaque classe utilitaire.
 *
 * La syntaxe `hsl(var(--x) / <alpha-value>)` exige que la variable contienne un
 * triplet HSL nu (« 199 89% 48% »), sans la fonction hsl(). C'est ce qui rend
 * `bg-brand/10` possible sans inventer un token par niveau d'opacité.
 */
const token = (name) => `hsl(var(--${name}) / <alpha-value>)`;

module.exports = {
  darkMode: 'class',
  content: [
    './templates/**/*.html',
    './devices/**/*.py',
    './static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          page: token('surface-page'),
          card: token('surface-card'),
          raised: token('surface-raised'),
          sunken: token('surface-sunken'),
          hover: token('surface-hover'),
        },
        border: {
          DEFAULT: token('border-subtle'),
          strong: token('border-strong'),
        },
        content: {
          DEFAULT: token('text-primary'),
          secondary: token('text-secondary'),
          subtle: token('text-subtle'),
          inverted: token('text-inverted'),
        },
        brand: {
          DEFAULT: token('brand'),
          hover: token('brand-hover'),
          subtle: token('brand-subtle'),
          on: token('brand-on'),
          text: token('brand-text'),
        },
        success: { DEFAULT: token('success'), subtle: token('success-subtle'), text: token('success-text'), on: token('success-on') },
        warning: { DEFAULT: token('warning'), subtle: token('warning-subtle'), text: token('warning-text'), on: token('warning-on') },
        danger:  { DEFAULT: token('danger'),  subtle: token('danger-subtle'),  text: token('danger-text')  , on: token('danger-on') },
        info:    { DEFAULT: token('info'),    subtle: token('info-subtle'),    text: token('info-text')    , on: token('info-on') },
        neutral: { DEFAULT: token('neutral'), subtle: token('neutral-subtle'), text: token('neutral-text'), on: token('neutral-on') },

        // ALIAS TEMPORAIRE — à supprimer au dernier commit de la migration.
        // Les gabarits pas encore repris utilisent encore `primary-600` : sans
        // cet alias, ils perdraient toute couleur dès le premier build.
        primary: {
          50: '#f0f9ff', 100: '#e0f2fe', 200: '#bae6fd', 300: '#7dd3fc',
          400: '#38bdf8', 500: '#0ea5e9', 600: '#0284c7', 700: '#0369a1',
          800: '#075985', 900: '#0c4a6e',
        },
      },
      borderRadius: {
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
      },
      boxShadow: {
        1: 'var(--shadow-1)',
        2: 'var(--shadow-2)',
        3: 'var(--shadow-3)',
      },
      // Entrees de page : une seule fois, a l'arrivee du contenu.
      animation: {
        'fade-in': 'fadeIn .4s ease-out',
        'slide-up': 'slideUp .3s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
};
