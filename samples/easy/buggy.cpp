#include <cstdio>
#include <cstdlib>
#include <cstring>

struct Item {
    int data;
    Item* link;
};

Item* mk_chain(int count) {
    Item* head = nullptr;
    for (int i = count; i > 0; --i) {
        Item* n = new Item;
        n->data = i * 10;
        n->link = head;
        head = n;
    }
    return head;
}

// BUG: use-after-free — frees a node then reads from it
void proc_a(Item* list) {
    Item* second = list->link;
    delete second;
    printf("got value: %d\n", second->data);
}

// BUG: stack buffer overrun — strcpy overflows an 8-byte buffer
int proc_b() {
    char buf[8];
    strcpy(buf, "This string is way too long for the buffer!");
    printf("result: %s\n", buf);
    return 0;
}

// BUG: null pointer dereference — writes through a null pointer
int proc_c() {
    int* p = nullptr;
    printf("entering proc_c...\n");
    *p = 42;
    return *p;
}

// BUG: integer divide by zero — divisor is hardcoded to 0
int proc_d(int x) {
    int d = 0;
    printf("computing with %d...\n", x);
    return x / d;
}

int main(int argc, char* argv[]) {
    printf("=== Sample Program ===\n\n");

    const char* mode = (argc > 1) ? argv[1] : "1";

    if (strcmp(mode, "1") == 0) {
        printf("[1] Running scenario...\n");
        proc_c();
    } else if (strcmp(mode, "2") == 0) {
        printf("[2] Running scenario...\n");
        proc_d(100);
    } else if (strcmp(mode, "3") == 0) {
        printf("[3] Running scenario...\n");
        Item* list = mk_chain(5);
        proc_a(list);
    } else if (strcmp(mode, "4") == 0) {
        printf("[4] Running scenario...\n");
        proc_b();
    } else {
        printf("Usage: buggy.exe [1|2|3|4]\n");
        return 0;
    }

    printf("\nDone.\n");
    return 0;
}
