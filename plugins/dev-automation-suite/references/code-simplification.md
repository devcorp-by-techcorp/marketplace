# Code Simplification — Detailed Reference

## Table of Contents

1. [Simplification Philosophy](#simplification-philosophy)
2. [Python Patterns](#python-patterns)
3. [JavaScript Patterns](#javascript-patterns)
4. [HTML/CSS Patterns](#htmlcss-patterns)
5. [Safety Rules](#safety-rules)

---

## Simplification Philosophy

Code simplification is the practice of improving how code is written without changing what it does. The goal is clarity, consistency, and maintainability — not fewer lines.

### Guiding Principles

1. **Explicit over clever**: Code that reads like prose beats code that reads like a puzzle
2. **Flat over nested**: Fewer indentation levels means easier comprehension
3. **Named over anonymous**: Named functions and variables communicate intent
4. **Consistent over optimal**: Following project patterns matters more than micro-optimisation
5. **Readable over compact**: A clear 10-line function beats a cryptic 3-line one

### When NOT to Simplify

- The code is already clear and follows project conventions
- Simplification would change behaviour (even subtly)
- The "simpler" version is actually harder to understand
- The abstraction being removed serves a genuine organisational purpose
- The change would break backwards compatibility

---

## Python Patterns

### Early Returns Over Deep Nesting

```python
# BEFORE: Nested conditionals
def process_order(order):
    if order is not None:
        if order.is_valid():
            if order.has_items():
                total = calculate_total(order)
                if total > 0:
                    return process_payment(order, total)
                else:
                    return Error('Empty total')
            else:
                return Error('No items')
        else:
            return Error('Invalid order')
    else:
        return Error('No order')

# AFTER: Guard clauses with early returns
def process_order(order):
    if order is None:
        return Error('No order')
    if not order.is_valid():
        return Error('Invalid order')
    if not order.has_items():
        return Error('No items')

    total = calculate_total(order)
    if total <= 0:
        return Error('Empty total')

    return process_payment(order, total)
```

### Named Booleans Over Complex Conditions

```python
# BEFORE: Complex inline condition
if (user.age >= 18 and user.verified and not user.banned
        and user.subscription_active and user.payment_valid):
    grant_access(user)

# AFTER: Named conditions
is_adult = user.age >= 18
is_eligible = user.verified and not user.banned
has_active_subscription = user.subscription_active and user.payment_valid

if is_adult and is_eligible and has_active_subscription:
    grant_access(user)
```

### Dictionary Dispatch Over Long If/Elif Chains

```python
# BEFORE: Long if/elif chain
def handle_action(action, data):
    if action == 'create':
        return create_item(data)
    elif action == 'update':
        return update_item(data)
    elif action == 'delete':
        return delete_item(data)
    elif action == 'archive':
        return archive_item(data)
    else:
        raise ValueError(f'Unknown action: {action}')

# AFTER: Dictionary dispatch
ACTION_HANDLERS = {
    'create': create_item,
    'update': update_item,
    'delete': delete_item,
    'archive': archive_item,
}

def handle_action(action, data):
    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        raise ValueError(f'Unknown action: {action}')
    return handler(data)
```

### List/Dict Comprehensions (When Clear)

```python
# BEFORE: Loop to build list
active_users = []
for user in users:
    if user.is_active:
        active_users.append(user.name)

# AFTER: Comprehension (clear and concise)
active_users = [user.name for user in users if user.is_active]

# BUT: Don't over-compress — keep it readable
# BAD: Nested comprehension that's hard to parse
result = [transform(x) for group in data for x in group.items if x.valid and x.score > threshold]

# BETTER: Use a helper or loop for complex logic
def get_valid_transformed_items(data, threshold):
    results = []
    for group in data:
        for item in group.items:
            if item.valid and item.score > threshold:
                results.append(transform(item))
    return results
```

### Context Managers for Resource Management

```python
# BEFORE: Manual cleanup
f = open('data.json', 'r')
try:
    data = json.load(f)
finally:
    f.close()

# AFTER: Context manager
with open('data.json', 'r') as f:
    data = json.load(f)
```

### String Formatting Consistency

```python
# Use f-strings consistently (project standard)
# NOT: 'Hello %s' % name
# NOT: 'Hello {}'.format(name)
# YES:
message = f'Hello {name}, you have {count} items'
```

---

## JavaScript Patterns

### Destructuring for Clarity

```javascript
// BEFORE: Repeated object access
function displayUser(user) {
    document.getElementById('name').textContent = user.name;
    document.getElementById('email').textContent = user.email;
    document.getElementById('role').textContent = user.role;
}

// AFTER: Destructure once
function displayUser(user) {
    const { name, email, role } = user;
    document.getElementById('name').textContent = name;
    document.getElementById('email').textContent = email;
    document.getElementById('role').textContent = role;
}
```

### Async/Await Over Promise Chains

```javascript
// BEFORE: Promise chain
function loadDashboard() {
    return fetchUser()
        .then(function(user) {
            return fetchOrders(user.id);
        })
        .then(function(orders) {
            return renderDashboard(orders);
        })
        .catch(function(error) {
            showError(error.message);
        });
}

// AFTER: Async/await
async function loadDashboard() {
    try {
        const user = await fetchUser();
        const orders = await fetchOrders(user.id);
        return renderDashboard(orders);
    } catch (error) {
        showError(error.message);
    }
}
```

### Template Literals Over Concatenation

```javascript
// BEFORE: String concatenation
var html = '<div class="' + className + '">' +
    '<h3>' + title + '</h3>' +
    '<p>' + description + '</p>' +
    '</div>';

// AFTER: Template literal
const html = `
    <div class="${className}">
        <h3>${title}</h3>
        <p>${description}</p>
    </div>
`;
```

### Avoid Nested Ternaries

```javascript
// BAD: Nested ternary — hard to read
const label = status === 'active' ? 'Active' :
    status === 'pending' ? 'Pending' :
    status === 'archived' ? 'Archived' : 'Unknown';

// GOOD: Switch statement or object lookup
const STATUS_LABELS = {
    active: 'Active',
    pending: 'Pending',
    archived: 'Archived',
};
const label = STATUS_LABELS[status] || 'Unknown';
```

---

## HTML/CSS Patterns

### Semantic HTML

```html
<!-- BEFORE: Div soup -->
<div class="header">
    <div class="nav">
        <div class="link">Home</div>
    </div>
</div>

<!-- AFTER: Semantic elements -->
<header>
    <nav>
        <a href="/">Home</a>
    </nav>
</header>
```

### Tailwind Utility Consolidation

```html
<!-- BEFORE: Redundant utilities -->
<div class="mt-4 mb-4 ml-4 mr-4 pt-2 pb-2">

<!-- AFTER: Shorthand utilities -->
<div class="m-4 py-2">
```

### Consistent Component Patterns

```html
<!-- Standard card pattern -->
<article class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
    <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
        {{ title }}
    </h3>
    <p class="mt-2 text-gray-600 dark:text-gray-400">
        {{ description }}
    </p>
</article>
```

---

## Safety Rules

### Pre-Simplification Checklist

Before simplifying any code:
- [ ] Original file backed up or version-controlled
- [ ] All public APIs documented in inventory
- [ ] All integration points mapped
- [ ] All test cases identified

### Post-Simplification Verification

After simplifying:
- [ ] All original functions still exist with identical signatures
- [ ] All original exports still present
- [ ] All tests still pass
- [ ] All integration points still work
- [ ] No new warnings or errors introduced
- [ ] Code is genuinely simpler (not just different)

### Forbidden Simplifications

| Action | Reason |
|--------|--------|
| Removing "unused" functions | May be used dynamically or by external code |
| Inlining helper functions | Reduces readability if helpers are well-named |
| Combining unrelated functions | Violates single responsibility |
| Removing type hints | Reduces code safety |
| Removing docstrings | Reduces documentation |
| Removing error handling | Reduces robustness |
| Replacing explicit code with magic | Reduces clarity |
