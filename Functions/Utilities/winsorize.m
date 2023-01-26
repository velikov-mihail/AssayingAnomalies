function wdata = winsorize(data,n) 

a = [n 100-n] ; 

for j = 1:rows(data)
    b = data(j,:);

    if sum(~isnan(b))>0
        p = prctile(b,a);
        b(b<p(1))=p(1);
        b(b>p(2))=p(2);
        data(j,:) = b;
    end
end

wdata = data;



    
