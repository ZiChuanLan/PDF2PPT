# Research: Modern SaaS UX Patterns

- **Query**: Modern SaaS dashboard and settings page UX patterns
- **Scope**: external + internal (web research + codebase analysis)
- **Date**: 2026-05-03

## Findings

### 1. Dashboard Patterns

#### Pattern: Hero Upload Area (Above the Fold)

**Description**: The primary action (file upload) is placed prominently at the top of the page with a large, visually distinctive dropzone. This follows the "one primary action per screen" principle.

**Why it works**:
- Reduces cognitive load by making the main action obvious
- Users can start working immediately without searching for controls
- The large dropzone target improves usability (Fitts's Law)

**Implementation notes** (Tailwind/shadcn):
```tsx
<div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-muted-foreground/25 bg-muted/50 p-8 transition-colors hover:border-muted-foreground/50 md:p-12">
  <UploadCloudIcon className="mb-4 size-12 text-muted-foreground" />
  <p className="text-lg font-medium">拖拽 PDF 或图片到这里</p>
  <p className="mt-1 text-sm text-muted-foreground">或点击选择文件</p>
</div>
```

**Examples**:
- Notion: Large upload area with drag-and-drop support
- Figma: Centered dropzone with clear visual hierarchy
- Canva: Prominent upload button with drag-and-drop overlay

**Current codebase**: `web/src/app/page.tsx:690-712` uses `react-dropzone` with similar pattern but could be more visually prominent.

---

#### Pattern: Progressive Disclosure in Settings

**Description**: Settings are organized into logical groups with collapsible sections. Common settings are visible by default, while advanced settings are hidden behind "Show more" or accordion toggles.

**Why it works**:
- Reduces overwhelm for new users
- Experts can access advanced options without friction
- Maintains a clean, focused interface

**Implementation notes** (Tailwind/shadcn):
```tsx
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"

<Accordion type="multiple" defaultValue={["basic"]}>
  <AccordionItem value="basic">
    <AccordionTrigger>基础配置</AccordionTrigger>
    <AccordionContent>
      {/* Common settings here */}
    </AccordionContent>
  </AccordionItem>
  <AccordionItem value="advanced">
    <AccordionTrigger>高级配置</AccordionTrigger>
    <AccordionContent>
      {/* Advanced settings here */}
    </AccordionContent>
  </AccordionItem>
</Accordion>
```

**Examples**:
- Vercel: Settings grouped by category with clear headers
- GitHub: Settings pages use progressive disclosure extensively
- Linear: Clean settings with collapsible sections

**Current codebase**: `web/src/app/settings/page.tsx:57-65` defines sections but uses flat layout (2545 lines, no folding).

---

#### Pattern: Card-Based Layout with Clear Hierarchy

**Description**: Content is organized into cards with consistent styling, clear headers, and logical grouping. Each card has a single responsibility.

**Why it works**:
- Creates visual separation between different functions
- Makes scanning easier with consistent patterns
- Provides clear boundaries for different features

**Implementation notes** (Tailwind/shadcn):
```tsx
<Card className="border-border shadow-sm">
  <CardHeader>
    <CardTitle>任务状态</CardTitle>
    <CardDescription>处理开始后，这里会持续刷新状态和进度</CardDescription>
  </CardHeader>
  <CardContent>
    {/* Content here */}
  </CardContent>
</Card>
```

**Examples**:
- Stripe: Dashboard uses cards for different metrics
- Linear: Task cards with clear hierarchy
- Notion: Card-based layouts for different content types

**Current codebase**: `web/src/app/page.tsx:959-1018` uses Card components but mixes multiple responsibilities.

---

### 2. Settings Page Patterns

#### Pattern: Grouped Settings with Visual Separation

**Description**: Settings are organized into logical groups with clear visual separation (borders, spacing, or background colors). Each group has a descriptive header.

**Why it works**:
- Users can quickly find related settings
- Reduces cognitive load by chunking information
- Creates a clear mental model of the system

**Implementation notes** (Tailwind/shadcn):
```tsx
<div className="space-y-6">
  <div className="rounded-lg border bg-card p-6">
    <h3 className="font-semibold">接口配置</h3>
    <p className="mt-1 text-sm text-muted-foreground">密钥与连接方式</p>
    <div className="mt-4 space-y-4">
      {/* API settings */}
    </div>
  </div>
  
  <div className="rounded-lg border bg-card p-6">
    <h3 className="font-semibold">处理策略</h3>
    <p className="mt-1 text-sm text-muted-foreground">输出方式与版式处理</p>
    <div className="mt-4 space-y-4">
      {/* Processing settings */}
    </div>
  </div>
</div>
```

**Examples**:
- Vercel: Settings grouped by domain (General, Environment Variables, etc.)
- GitHub: Clear section headers with descriptive text
- Netlify: Settings organized by feature area

**Current codebase**: `web/src/app/settings/page.tsx:57-65` defines sections but uses flat layout.

---

#### Pattern: Sensitive Field Protection

**Description**: API keys and sensitive information use password input fields with show/hide toggles. This prevents accidental exposure while maintaining usability.

**Why it works**:
- Prevents shoulder surfing
- Reduces accidental exposure in screenshots
- Users can verify the value when needed

**Implementation notes** (Tailwind/shadcn):
```tsx
<div className="relative">
  <Input
    type={showKey ? "text" : "password"}
    value={apiKey}
    onChange={(e) => setApiKey(e.target.value)}
  />
  <Button
    type="button"
    variant="ghost"
    size="icon"
    className="absolute right-2 top-1/2 -translate-y-1/2"
    onClick={() => setShowKey(!showKey)}
  >
    {showKey ? <EyeOffIcon className="size-4" /> : <EyeIcon className="size-4" />}
  </Button>
</div>
```

**Examples**:
- Vercel: API keys shown as masked with copy button
- GitHub: Tokens shown as masked with reveal option
- AWS: Secret keys hidden by default

**Current codebase**: `web/src/app/settings/page.tsx` uses `SENSITIVE_KEYS` from `web/src/hooks/use-settings.ts` but implementation details unclear.

---

#### Pattern: Inline Validation with Clear Feedback

**Description**: Form fields show validation errors inline, close to the field that has the issue. Error messages are specific and actionable.

**Why it works**:
- Users can immediately see what needs fixing
- Reduces frustration from trial-and-error
- Prevents form submission with invalid data

**Implementation notes** (Tailwind/shadcn):
```tsx
<div className="space-y-2">
  <Label htmlFor="email">Email</Label>
  <Input
    id="email"
    type="email"
    value={email}
    onChange={(e) => setEmail(e.target.value)}
    className={cn(error && "border-destructive")}
  />
  {error && (
    <p className="text-sm text-destructive">{error}</p>
  )}
</div>
```

**Examples**:
- Stripe: Real-time validation with clear error messages
- Linear: Inline validation with helpful suggestions
- Notion: Non-intrusive validation feedback

---

### 3. File Upload Patterns

#### Pattern: Multi-State Dropzone

**Description**: The upload area shows different states: empty (invitation to upload), drag-over (visual feedback), uploading (progress), and complete (preview).

**Why it works**:
- Provides clear feedback at every stage
- Reduces uncertainty about what's happening
- Creates a smooth user journey

**Implementation notes** (Tailwind/shadcn):
```tsx
<div
  className={cn(
    "border-2 border-dashed rounded-lg p-8 transition-all",
    isDragActive 
      ? "border-primary bg-primary/5 scale-[1.02]" 
      : "border-muted-foreground/25 hover:border-muted-foreground/50"
  )}
>
  {isDragActive ? (
    <p>松开以上传文件</p>
  ) : file ? (
    <div>{/* File preview */}</div>
  ) : (
    <div>{/* Upload invitation */}</div>
  )}
</div>
```

**Examples**:
- Notion: Smooth drag-over animation
- Figma: Clear state changes during upload
- Canva: Visual feedback for different file types

**Current codebase**: `web/src/app/page.tsx:690-712` implements this pattern but could enhance drag-over feedback.

---

#### Pattern: Immediate Preview After Upload

**Description**: After uploading, the file preview appears immediately, giving users instant feedback that their upload was successful.

**Why it works**:
- Confirms the upload was successful
- Users can verify they uploaded the correct file
- Reduces anxiety about whether the upload worked

**Implementation notes** (Tailwind/shadcn):
```tsx
{file && (
  <div className="mt-4">
    <div className="flex items-center justify-between rounded-md border bg-muted/50 p-3">
      <div className="flex items-center gap-3">
        <FileIcon className="size-8 text-muted-foreground" />
        <div>
          <p className="font-medium">{file.name}</p>
          <p className="text-sm text-muted-foreground">{formatBytes(file.size)}</p>
        </div>
      </div>
      <Button variant="ghost" size="icon" onClick={clearFile}>
        <XIcon className="size-4" />
      </Button>
    </div>
    {/* Preview component */}
  </div>
)}
```

**Examples**:
- Notion: Immediate preview of uploaded files
- Figma: Shows file thumbnail after upload
- Canva: Instant preview with edit options

**Current codebase**: `web/src/app/page.tsx:714-733` shows file info but preview is in a separate area.

---

#### Pattern: Clear File Constraints

**Description**: Before upload, users see what file types and sizes are accepted. This prevents failed uploads and frustration.

**Why it works**:
- Sets clear expectations upfront
- Reduces failed uploads
- Saves user time

**Implementation notes** (Tailwind/shadcn):
```tsx
<p className="mt-2 text-xs text-muted-foreground">
  支持 .pdf .png .jpg .jpeg .webp
</p>
```

**Examples**:
- Notion: Clear file type restrictions shown
- Figma: Shows supported formats before upload
- Canva: Displays file size limits

**Current codebase**: `web/src/app/page.tsx:704-706` shows supported formats.

---

### 4. Progress/Status Patterns

#### Pattern: Stepped Progress Indicator

**Description**: Progress is shown as a series of steps or stages, with the current step highlighted and completed steps marked.

**Why it works**:
- Users understand where they are in the process
- Provides a sense of control and predictability
- Reduces anxiety about unknown wait times

**Implementation notes** (Tailwind/shadcn):
```tsx
<div className="flex items-center gap-2">
  {steps.map((step, index) => (
    <div key={step} className="flex items-center gap-2">
      <div
        className={cn(
          "flex size-8 items-center justify-center rounded-full border-2 text-sm font-medium",
          index < currentStep
            ? "border-primary bg-primary text-primary-foreground"
            : index === currentStep
            ? "border-primary text-primary"
            : "border-muted-foreground/25 text-muted-foreground"
        )}
      >
        {index < currentStep ? <CheckIcon className="size-4" /> : index + 1}
      </div>
      {index < steps.length - 1 && (
        <div
          className={cn(
            "h-0.5 w-8",
            index < currentStep ? "bg-primary" : "bg-muted-foreground/25"
          )}
        />
      )}
    </div>
  ))}
</div>
```

**Examples**:
- Linear: Clear step indicators for workflows
- GitHub: Progress bars for multi-step processes
- Notion: Step-by-step progress for imports

**Current codebase**: `web/src/app/page.tsx:1016-1038` implements stepped progress with `JOB_STAGE_FLOW`.

---

#### Pattern: Real-Time Status Updates

**Description**: Status updates appear in real-time without requiring page refresh. This includes progress percentages, stage labels, and status messages.

**Why it works**:
- Users don't need to manually refresh
- Provides continuous feedback
- Reduces uncertainty about what's happening

**Implementation notes** (Tailwind/shadcn):
```tsx
<div className="space-y-2">
  <div className="flex items-center justify-between text-sm">
    <span>进度</span>
    <span>{progress}%</span>
  </div>
  <Progress value={progress} className="h-2" />
  <p className="text-sm text-muted-foreground">{statusMessage}</p>
</div>
```

**Examples**:
- Vercel: Real-time deployment progress
- Netlify: Live build status updates
- Linear: Real-time task status changes

**Current codebase**: `web/src/app/page.tsx:509-559` implements polling for status updates.

---

#### Pattern: Toast Notifications for Terminal States

**Description**: When a task completes or fails, a toast notification appears to inform the user, even if they've navigated away.

**Why it works**:
- Users don't miss important updates
- Provides clear feedback for completed actions
- Non-intrusive notification pattern

**Implementation notes** (Tailwind/shadcn):
```tsx
import { toast } from "sonner"

if (status === "completed") {
  toast.success("转换完成，可下载 PPTX")
} else if (status === "failed") {
  toast.error(errorMessage)
}
```

**Examples**:
- Vercel: Deployment success/failure toasts
- GitHub: Action completion notifications
- Linear: Task status change notifications

**Current codebase**: `web/src/app/page.tsx:575-581` implements toast notifications for terminal states.

---

### 5. Mobile-First Patterns

#### Pattern: Responsive Grid Layout

**Description**: Layout uses responsive grid that adapts from single column on mobile to multi-column on desktop.

**Why it works**:
- Content is accessible on all devices
- No horizontal scrolling on mobile
- Optimal use of screen real estate

**Implementation notes** (Tailwind/shadcn):
```tsx
<div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
  {/* Cards */}
</div>
```

**Examples**:
- Notion: Responsive grid for content blocks
- Linear: Adaptive layout for different screen sizes
- GitHub: Responsive dashboard layout

**Current codebase**: `web/src/app/page.tsx:675` uses `xl:grid-cols-[minmax(0,1fr)_280px]` but could be more responsive.

---

#### Pattern: Collapsible Navigation on Mobile

**Description**: Navigation collapses into a hamburger menu or drawer on mobile, expanding to a sidebar on desktop.

**Why it works**:
- Saves screen space on mobile
- Maintains full navigation access
- Familiar pattern for mobile users

**Implementation notes** (Tailwind/shadcn):
```tsx
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"

<div className="md:hidden">
  <Sheet>
    <SheetTrigger asChild>
      <Button variant="ghost" size="icon">
        <MenuIcon className="size-5" />
      </Button>
    </SheetTrigger>
    <SheetContent side="left">
      {/* Navigation items */}
    </SheetContent>
  </Sheet>
</div>
```

**Examples**:
- Notion: Collapsible sidebar on mobile
- Linear: Mobile navigation drawer
- GitHub: Responsive navigation

**Current codebase**: `web/src/components/workbench-nav.tsx` uses sticky top bar but no mobile collapse.

---

#### Pattern: Touch-Friendly Targets

**Description**: Interactive elements (buttons, links, inputs) have minimum touch target sizes (44x44px recommended by Apple, 48x48px by Google).

**Why it works**:
- Prevents accidental taps
- Improves usability on touch devices
- Accessibility best practice

**Implementation notes** (Tailwind/shadcn):
```tsx
<Button className="min-h-[44px] min-w-[44px]">
  {/* Button content */}
</Button>
```

**Examples**:
- iOS apps: Consistent touch target sizes
- Material Design: 48dp minimum touch targets
- Tailwind UI: Accessible component sizes

---

## Implementation Priority Matrix

Based on the current codebase analysis and PRD requirements:

| Pattern | Impact | Effort | Priority |
|---------|--------|--------|----------|
| Hero Upload Area | High | Low | P0 |
| Progressive Disclosure | High | Medium | P0 |
| Stepped Progress | High | Medium | P0 |
| Card-Based Layout | Medium | Low | P1 |
| Sensitive Field Protection | Medium | Low | P1 |
| Responsive Grid | Medium | Low | P1 |
| Toast Notifications | Low | Low | P2 |
| Mobile Navigation | Low | Medium | P2 |

---

## Related Specs

- `.trellis/spec/frontend/index.md` — Frontend coding guidelines
- `.trellis/spec/guides/code-reuse-thinking-guide.md` — Code reuse patterns
- `.trellis/spec/guides/cross-layer-thinking-guide.md` — Cross-layer data flow

## Caveats / Not Found

- Could not access some design pattern resources (404 errors)
- Limited information on specific SaaS product implementations (proprietary)
- Mobile-first patterns section is less detailed due to limited mobile-specific research
