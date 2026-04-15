/*
 * samples/hard/challenge.cpp
 *
 * A "task scheduler" that processes work items from a priority queue.
 * Contains 3 subtle bugs that require careful debugging to find.
 *
 * Build (MSVC, debug, x64):
 *   cl /Zi /Od /EHsc /Fe:challenge.exe challenge.cpp
 *
 * Usage:
 *   challenge.exe           (runs all tasks)
 *
 * Bug descriptions (for answer key only — do NOT read before debugging):
 *
 *   Bug 1: SIGNED INTEGER OVERFLOW → WRONG ALLOCATION SIZE
 *     In compute_buffer_size(), the multiplication of two controlled int32
 *     values overflows, wrapping to a small positive number. The caller then
 *     allocates a too-small buffer and the subsequent memset writes past it.
 *     This is a classic heap buffer overflow caused by integer overflow in
 *     a size calculation.
 *
 *   Bug 2: OFF-BY-ONE IN CIRCULAR BUFFER → OUT-OF-BOUNDS WRITE
 *     The circular buffer's enqueue function uses (tail + 1) % capacity to
 *     advance the tail pointer — but capacity was allocated as N elements
 *     while the modular arithmetic allows tail to reach index N, writing
 *     one element past the end of the allocation. The off-by-one is in the
 *     relationship between the allocated size and the modulus.
 *
 *   Bug 3: DOUBLE-FREE VIA ALIASED POINTERS
 *     Two task structures end up pointing to the same dynamically-allocated
 *     payload buffer (via shallow copy in transfer_task). When both tasks
 *     are cleaned up in sequence, the payload is freed twice. The second
 *     free corrupts the heap.
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>

/* ---- data structures --------------------------------------------------- */

struct Payload {
    char* data;
    int   length;
};

struct Task {
    int      id;
    int      priority;
    Payload  payload;
};

struct Ring {
    Task** items;
    int    head;
    int    tail;
    int    capacity;
    int    count;
};

/* ---- helpers ----------------------------------------------------------- */

static int compute_buffer_size(int rows, int cols) {
    /* Bug 1: signed int multiplication overflows for large inputs.
       e.g. 50000 * 50000 = 2,500,000,000 which exceeds INT_MAX (2,147,483,647)
       and wraps to a small (or negative) value. The cast to size_t happens
       AFTER the overflow, so the damage is done. */
    int total = rows * cols;
    return total;
}

static Ring* create_ring(int n) {
    Ring* r = (Ring*)malloc(sizeof(Ring));
    r->items = (Task**)calloc(n, sizeof(Task*));
    r->head = 0;
    r->tail = 0;
    /* Bug 2 setup: we store capacity = n, but the modular arithmetic
       in enqueue uses (capacity + 1) as the modulus in some paths,
       allowing tail to reach index n — one past the allocation. */
    r->capacity = n;
    r->count = 0;
    return r;
}

static int ring_enqueue(Ring* r, Task* t) {
    if (r->count >= r->capacity)
        return -1;
    r->items[r->tail] = t;
    /* Bug 2: should be (r->tail + 1) % r->capacity, but uses
       (capacity + 1) as modulus. When tail == capacity-1, the next
       value is capacity % (capacity+1) == capacity, which is OUT OF
       BOUNDS for an array of size capacity. */
    r->tail = (r->tail + 1) % (r->capacity + 1);
    r->count++;
    return 0;
}

static Task* ring_dequeue(Ring* r) {
    if (r->count <= 0)
        return nullptr;
    Task* t = r->items[r->head];
    r->head = (r->head + 1) % (r->capacity + 1);
    r->count--;
    return t;
}

static void free_ring(Ring* r) {
    free(r->items);
    free(r);
}

static Task* create_task(int id, int priority, const char* msg) {
    Task* t = (Task*)malloc(sizeof(Task));
    t->id = id;
    t->priority = priority;
    int len = (int)strlen(msg) + 1;
    t->payload.data = (char*)malloc(len);
    memcpy(t->payload.data, msg, len);
    t->payload.length = len;
    return t;
}

static void transfer_task(Task* dst, const Task* src) {
    /* Bug 3: shallow copy of payload — dst->payload.data now aliases
       src->payload.data. When both are freed, it's a double-free. */
    dst->id = src->id;
    dst->priority = src->priority;
    dst->payload = src->payload;  /* copies the pointer, not the data */
}

static void free_task(Task* t) {
    if (t) {
        free(t->payload.data);
        t->payload.data = nullptr;
        free(t);
    }
}

/* ---- processing pipeline ----------------------------------------------- */

static void process_stage_a(Ring* q) {
    /* Stage A: compute a transform buffer size from task metadata.
       The values 50000 come from a simulated "config" — in real code
       these might be image dimensions, network packet counts, etc. */
    int rows = 50000;
    int cols = 50000;
    int size = compute_buffer_size(rows, cols);

    printf("  [A] buffer size = %d\n", size);

    if (size <= 0) {
        printf("  [A] invalid size, skipping\n");
        return;
    }

    /* The allocation uses the overflowed (small) size,
       but memset uses the intended large count. */
    char* buf = (char*)malloc((size_t)size);
    if (!buf) {
        printf("  [A] allocation failed\n");
        return;
    }

    /* Bug 1 trigger: memset with 4096 bytes into a buffer that may
       be much smaller due to the integer overflow above. */
    memset(buf, 0x41, 4096);

    printf("  [A] buffer filled OK\n");
    free(buf);
}

static void process_stage_b(Ring* q) {
    /* Stage B: fill the ring buffer to capacity.
       Bug 2 triggers here — the off-by-one in tail causes an
       out-of-bounds write on the last enqueue. */
    printf("  [B] enqueuing tasks\n");
    for (int i = 0; i < q->capacity; i++) {
        char msg[64];
        sprintf(msg, "item_%d", i);
        Task* t = create_task(100 + i, i % 5, msg);
        ring_enqueue(q, t);
    }
    printf("  [B] enqueued %d items\n", q->count);
}

static void process_stage_c(Ring* q) {
    /* Stage C: transfer a task to a "backup" and then free both.
       Bug 3 triggers here — the shallow copy causes double-free. */
    Task* original = ring_dequeue(q);
    if (!original) return;

    Task* backup = (Task*)malloc(sizeof(Task));
    memset(backup, 0, sizeof(Task));

    transfer_task(backup, original);

    printf("  [C] transferred task %d\n", backup->id);

    /* Free the original — this frees payload.data */
    free_task(original);

    /* Free the backup — payload.data is the SAME pointer → double free */
    free_task(backup);

    printf("  [C] cleanup done\n");
}

/* ---- main -------------------------------------------------------------- */

int main() {
    printf("== Task Scheduler ==\n");

    Ring* queue = create_ring(8);

    printf("[1] Processing stage A...\n");
    process_stage_a(queue);

    printf("[2] Processing stage B...\n");
    process_stage_b(queue);

    printf("[3] Processing stage C...\n");
    process_stage_c(queue);

    /* Drain remaining tasks */
    printf("[4] Draining queue...\n");
    Task* t;
    while ((t = ring_dequeue(queue)) != nullptr) {
        printf("  drained task %d\n", t->id);
        free_task(t);
    }

    free_ring(queue);
    printf("== Done ==\n");
    return 0;
}
