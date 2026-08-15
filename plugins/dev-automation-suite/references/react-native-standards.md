# React Native Code Quality Standards

## Table of Contents

1. [Component Quality](#component-quality)
2. [Navigation Patterns](#navigation-patterns)
3. [Native Module Compatibility](#native-module-compatibility)
4. [Performance Patterns](#performance-patterns)
5. [Expo-Specific Standards](#expo-specific-standards)
6. [NativeWind / Tailwind CSS Standards](#nativewind--tailwind-css-standards)
7. [TypeScript Standards](#typescript-standards)

---

## Component Quality

### Rules of Hooks

Hook calls must appear at the top level of the component or custom hook body — never inside conditionals, loops, callbacks, or try/catch blocks.

```tsx
// Correct — hooks at top level
function UserProfile({ userId }: Props) {
  const [user, setUser] = useState<User | null>(null);
  const navigation = useNavigation<ProfileNavProp>();

  useEffect(() => {
    fetchUser(userId).then(setUser);
  }, [userId]);

  if (!user) return <LoadingSpinner />;
  return <ProfileCard user={user} />;
}

// Incorrect — hook inside conditional
function UserProfile({ userId }: Props) {
  if (userId) {
    const [user, setUser] = useState(null); // VIOLATION
  }
}
```

### Props and Type Definitions

Define explicit TypeScript interfaces for all component props. Avoid `any` and loose object types.

```tsx
// Correct
interface CardProps {
  title: string;
  subtitle?: string;
  onPress: () => void;
  children: React.ReactNode;
}

export function Card({ title, subtitle, onPress, children }: CardProps) {
  // ...
}
```

### State Management

- Prefer `useState` for local UI state.
- Use `useReducer` for complex state transitions with multiple sub-values.
- Avoid storing derived values in state — compute during render or use `useMemo`.
- Lift state only as high as necessary.

```tsx
// Derived value — do NOT put in state
function OrderSummary({ items }: { items: LineItem[] }) {
  const total = useMemo(
    () => items.reduce((sum, i) => sum + i.price * i.qty, 0),
    [items],
  );
  // ...
}
```

### Custom Hooks

Extract reusable logic into custom hooks prefixed with `use`. Each custom hook should:

- Have a clear single responsibility
- Accept typed parameters
- Return a well-defined typed value or tuple
- Include a JSDoc description

---

## Navigation Patterns

### React Navigation (Stack, Tab, Drawer)

Type every navigator and screen to catch route-name typos and missing params at compile time.

```tsx
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";

type RootStackParamList = {
  Home: undefined;
  Profile: { userId: string };
  Settings: undefined;
};

type ProfileScreenNavProp = NativeStackNavigationProp<RootStackParamList, "Profile">;
type ProfileScreenRouteProp = RouteProp<RootStackParamList, "Profile">;

function ProfileScreen() {
  const navigation = useNavigation<ProfileScreenNavProp>();
  const route = useRoute<ProfileScreenRouteProp>();
  const { userId } = route.params;
  // ...
}
```

### Expo Router

Expo Router uses file-based routing. Standards:

- Place route files under `app/` following the directory convention.
- Use typed `useLocalSearchParams<T>()` and `useGlobalSearchParams<T>()`.
- Define `_layout.tsx` files for every route group to control navigation structure.
- Prefer `<Link href="/profile/123">` over imperative `router.push()` for static navigation.

```tsx
// app/profile/[id].tsx
import { useLocalSearchParams } from "expo-router";

interface ProfileParams {
  id: string;
}

export default function ProfileScreen() {
  const { id } = useLocalSearchParams<ProfileParams>();
  // ...
}
```

### Deep Linking

- Register URL schemes in `app.json` / `app.config.ts` (Expo) or `AndroidManifest.xml` / `Info.plist` (bare).
- Validate all deep-link parameters before use.
- Provide fallback screens for unrecognized routes.

---

## Native Module Compatibility

### Platform Guards

Every call to a native module or platform-specific API must be guarded by `Platform.OS` or `Platform.select`.

```tsx
import { Platform, NativeModules } from "react-native";

const BiometricModule =
  Platform.OS === "ios"
    ? NativeModules.FaceIDModule
    : NativeModules.FingerprintModule;

// Or using Platform.select
const hapticFeedback = Platform.select({
  ios: () => NativeModules.HapticEngine.trigger(),
  android: () => NativeModules.Vibration.vibrate(50),
  default: () => {},
});
```

### Expo Modules

When using Expo modules (e.g., `expo-camera`, `expo-location`):

- Always check permissions before accessing hardware.
- Handle the case where the module is unavailable (web, older devices).
- Prefer the Expo wrapper over direct `NativeModules` access for managed workflow compatibility.

```tsx
import * as Location from "expo-location";

async function getLocation() {
  const { status } = await Location.requestForegroundPermissionsAsync();
  if (status !== "granted") {
    throw new PermissionError("Location permission denied");
  }
  return Location.getCurrentPositionAsync({});
}
```

### TurboModules and New Architecture

- Guard `TurboModuleRegistry` lookups with `Platform.OS` checks.
- Verify the native module is non-null before invoking methods.
- Provide JavaScript fallbacks where feasible for web/unsupported platforms.

---

## Performance Patterns

### Memoization

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `React.memo()` | Skip re-rendering when props unchanged | Wrap pure presentational components receiving non-primitive props |
| `useMemo()` | Cache expensive computed values | Derived data, filtered/sorted lists, complex calculations |
| `useCallback()` | Stabilise function references | Handlers passed as props to memoized children or FlatList |

Do not memoize everything — measure first. Unnecessary memoization adds overhead.

### FlatList / SectionList / FlashList

Required props for performant lists:

```tsx
<FlatList
  data={items}
  renderItem={renderItem}        // Stable reference (useCallback)
  keyExtractor={keyExtractor}    // Stable, unique key per item
  getItemLayout={getItemLayout}  // When item height is fixed
  removeClippedSubviews          // Reduces off-screen rendering (Android)
  maxToRenderPerBatch={10}       // Tune per use case
  windowSize={5}                 // Reduce memory footprint
/>
```

Anti-patterns to avoid:

- Inline `renderItem` arrow functions (creates new reference each render)
- Missing `keyExtractor` (causes full list re-render on data change)
- Nesting `FlatList` inside `ScrollView` (breaks virtualisation)

### Re-render Prevention

- Extract child components and wrap with `React.memo`.
- Use `useCallback` for handlers passed to children.
- Avoid object/array literals in JSX props — extract to constants or `useMemo`.
- Prefer `StyleSheet.create()` over inline style objects.

### Image Optimisation

- Use `expo-image` or `react-native-fast-image` for cached/remote images.
- Specify explicit `width` and `height` to avoid layout thrash.
- Use appropriate resize modes and quality settings.

---

## Expo-Specific Standards

### Configuration

- Use `app.config.ts` (TypeScript) over `app.json` for dynamic configuration.
- Keep secrets out of config — use `expo-constants` with `.env` files.
- Pin SDK and dependency versions to avoid upgrade drift.

### EAS Build and Updates

- Configure `eas.json` with separate `development`, `preview`, and `production` profiles.
- Use `expo-updates` for OTA updates — never ship native code changes via OTA.
- Test builds with `--profile preview` before production releases.

### Managed vs Bare Workflow

When using native modules unavailable in managed Expo:

1. Prefer Expo config plugins over ejecting.
2. If bare workflow is required, document the native setup in `NATIVE_SETUP.md`.
3. Keep `ios/` and `android/` directories in `.gitignore` if using prebuild.

---

## NativeWind / Tailwind CSS Standards

### Usage Patterns

```tsx
// Correct — className prop with Tailwind utilities
function Badge({ label }: { label: string }) {
  return (
    <View className="rounded-full bg-blue-500 px-3 py-1">
      <Text className="text-sm font-medium text-white">{label}</Text>
    </View>
  );
}

// Avoid mixing className and style prop
// Use one styling approach consistently per component
```

### Platform-Specific Classes

Use NativeWind platform modifiers when styles differ between platforms:

```tsx
<View className="p-4 ios:pt-12 android:pt-6" />
```

### Dark Mode

Use the `dark:` variant consistently:

```tsx
<View className="bg-white dark:bg-gray-900">
  <Text className="text-gray-900 dark:text-gray-100">{content}</Text>
</View>
```

---

## TypeScript Standards

### Strict Mode

Enable `strict: true` in `tsconfig.json`. Specific requirements:

- No `any` in component props, state, or hook return types.
- Explicit return types on exported functions and custom hooks.
- Use `unknown` instead of `any` for dynamic external data; narrow with type guards.

### Navigation Types

Always generate and maintain a central `navigation.d.ts` or param-list type file:

```tsx
// types/navigation.ts
export type RootStackParamList = {
  Home: undefined;
  Profile: { userId: string };
  Settings: { section?: "account" | "notifications" };
};

declare global {
  namespace ReactNavigation {
    interface RootParamList extends RootStackParamList {}
  }
}
```

### API Response Types

Define explicit types for all API responses. Never trust runtime shapes without validation:

```tsx
import { z } from "zod";

const UserSchema = z.object({
  id: z.string(),
  name: z.string(),
  email: z.string().email(),
});

type User = z.infer<typeof UserSchema>;

async function fetchUser(id: string): Promise<User> {
  const response = await fetch(`/api/users/${id}`);
  const data = await response.json();
  return UserSchema.parse(data);
}
```
