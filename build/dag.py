from collections import defaultdict

class DAG:
    def __init__(self):
        self.builds = defaultdict(str)
        self.nodes = set()
        self.edges = defaultdict(list)
        self.dep_count = defaultdict(int)

    def add_edge(self, from_node, to_node, build):
        self.nodes.add(from_node)
        self.nodes.add(to_node)
        self.edges[from_node].append(to_node)
        self.dep_count[to_node] += 1
        self.builds[to_node] = build

    def topological_sort(self):
        # list of nodes with no incoming edges
        queue = [node for node in self.nodes if self.dep_count[node] == 0]

        # list to store the sorted nodes
        result = []

        # process nodes without incoming edges
        while queue:
            node = queue.pop(0)
            if node in self.builds:
                result.append(self.builds[node])
            else:
                print("Assuming %s is an external dependency because it has no config defined!" % node)
            for neighbor in self.edges[node]:
                self.dep_count[neighbor] -= 1
                if self.dep_count[neighbor] == 0:
                    queue.append(neighbor)

        # ensure that the graph does not have a cyclic dependency
        # note: This doesn't work yet
        circular_nodes = [node for node in self.nodes if self.dep_count[node] != 0 and node in self.config]
        if circular_nodes:
            raise ValueError('The input files have a circular dependency: %s' % circular_nodes)
        return result

