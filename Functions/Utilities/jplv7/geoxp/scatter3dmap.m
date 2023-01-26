function [out]=scatter3dmap(long,lat,var1,var2,var3,varargin)
% PURPOSE: This function links a map and a three-dimensionnal scatterplot
%------------------------------------------------------------------------
% USAGE: out=scatter3dmap(long,lat,var1,var2,var3,qvar,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           var1 = n x 1 vector of the variable to study on the first axis
%           var2 = n x 1 vector of the variable to study on the second axis
%           var3= n x 1 vector of the variable to study on the third axis
%           qvar = qualitative variable
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% MANUAL: Select points on either the map or the scatterplot by clicking with the left mouse button
%         You can select points inside a polygon on the map: - right click to set the first point of the polygon
%                                                 - left click to set the other points
%                                                 - right click to close the polygon
%         You can select points that have the same qvar value by pushing buttons 0-9 on the keybord.
%         Use the arrows of the i-j-k-l keys to rotate the 3D scatterplot
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses selectmap.m, selectstat.m
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
c=0;
l=0;
symbol=0;
affc=-1;
class=0; %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

vectx=[];
vecty=[];
name1=inputname(3);
name2=inputname(4);
name3=inputname(5);



%creation of a menu to save
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save scat3dfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%



% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        qvar=varargin{1};
        class=1;
        qname=inputname(6);
    end;
      
    if t>=2 & ~isempty(varargin{2})
        carte=varargin{2};
        c=1;
    end;
    if t>=3 & ~isempty(varargin{3})
        label=varargin{3};
        l=1;
    end;
    if t==4 & ~isempty(varargin{4})
        symbol=varargin{4};
    end;
end;

%%%%%%%%%%%%%%%%%%%%%


if class==1
    col{1}=[220/255,210/255,183/255];
    col{2}=[207/255,203/255,18/255];
    col{3}=[240/255,134/255,214/255];
    col{4}=[254/255,194/255,203/255];
    col{5}=[150/255,118/255,133/255];
    col{6}=[132/255,221/255,160/255];
    col{7}=[92/255,133/255,94/255];
    col{8}=[233/255,168/255,97/255];
    col{9}=[121/255,50/255,6/255];
    col{10}=[158/255,216/255,235/255];
    qvarsort=sort(qvar);
    N=histc(qvar,qvarsort');
    qvalues=qvarsort(find(N~=0));
    nbc=length(qvalues);
    affc=zeros(nbc,1);
    vectclass=cell(1,nbc);
    Hbutt=zeros(nbc,1);
    for i=1:nbc
        vectclass{i}=find(qvar==qvalues(i));
        Hbutt(i)=uicontrol('Style','togglebutton','string',[qname,'=',num2str(qvalues(i))],'BackGroundColor',col{i},'Units','Normalized','Position',[0.14+(i-1)*0.06,0.025,0.047,0.026],'Enable','inactive');
    end;   
end;


% Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
%%%%%%%%%%%%%%%%%%%%%

% Trace the scatter plot

Axis2=subplot(1,2,2);
plot3(var1,var2,var3,'b.');
title('Scatter Plot');
xlabel(name1);
ylabel(name2);
zlabel(name3);
axis manual;
subplot(Axis1);
axis manual;

Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');
%%%%%%%%%%%%%%%%%%%%%

% Main loop
maptest=0;
scattertest=0;
BUTTON=0;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    if ~isempty(Iunselect)
      plot3(var1(Iunselect),var2(Iunselect),var3(Iunselect),'b.');
    end;
    
    
    
    if class==1
        for i=1:nbc
            if affc(i)==1
                plot3(var1(vectclass{i}),var2(vectclass{i}),var3(vectclass{i}),'.','color',col{i}); %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
            end;        
        end;
    end;
    
    
    if ~isempty(Iselect) & BUTTON~=49 & BUTTON~=50 & BUTTON~=51 & BUTTON~=52 & BUTTON~=53 & BUTTON~=54 & BUTTON~=55 & BUTTON~=56 & BUTTON~=57 & BUTTON~=48
        if maptest==1
            if symbol==1
                plot3(var1(Iselect),var2(Iselect),var3(Iselect),'r*');
            else
                plot3(var1(Iselect),var2(Iselect),var3(Iselect),'r.');
            end;
        elseif scattertest==1
            if symbol==1
                plot3(var1(Iselect),var2(Iselect),var3(Iselect),'mo');
            else
                plot3(var1(Iselect),var2(Iselect),var3(Iselect),'m.'); 
            end;
        end;
    end;
    
    hold off;
    subplot(Axis1);
    hold on;
    cla;
    if c==1
        plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;
    
    if class==1
        for i=1:nbc
            if affc(i)==1
                plot(long(vectclass{i}),lat(vectclass{i}),'.','color',col{i}); %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
                if l==1
                    Htex=text(long(vectclass{i}),lat(vectclass{i}),num2str(label(vectclass{i})));
                    set(Htex,'FontSize',8);
                end;
            end;        
        end;
    end;
    
    
    if ~isempty(Iselect) & BUTTON~=49 & BUTTON~=50 & BUTTON~=51 & BUTTON~=52 & BUTTON~=53 & BUTTON~=54 & BUTTON~=55 & BUTTON~=56 & BUTTON~=57 & BUTTON~=48
        if maptest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'r*');
            else
                plot(long(Iselect),lat(Iselect),'r.');
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif scattertest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'mo');
            else
                plot(long(Iselect),lat(Iselect),'m.');              
            end;
        end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    
    if BUTTON==28 | BUTTON==106
        subplot(Axis2);
        [az,el]=view;
        view(az+10,el);
        continue;
    elseif BUTTON==29 | BUTTON==108
        subplot(Axis2);
        [az,el]=view;
        view(az-10,el);
        continue;
    elseif BUTTON==30 | BUTTON==105
        subplot(Axis2);
        [az,el]=view;
        if el<80
            view(az,el+10);
        else
            view(az,90);
        end;
        continue;
    elseif BUTTON==31 | BUTTON==107
        subplot(Axis2);
        [az,el]=view;
        if el>-80
            view(az,el-10);
        else
            view(az,-90);
        end;
        continue;
    end;
    
    if class==1
        if (BUTTON==49 | BUTTON==50 | BUTTON==51 | BUTTON==52 | BUTTON==53 | BUTTON==54 | BUTTON==55 | BUTTON==56 | BUTTON==57 | BUTTON==48) & isempty(find(affc~=0))
            obs=zeros(size(long,1),1);
            maptest=0;
            scattertest=0;
        end;
    end;
    % class selection
    if (BUTTON==49 | BUTTON==50 | BUTTON==51 | BUTTON==52 | BUTTON==53 | BUTTON==54 | BUTTON==55 | BUTTON==56 | BUTTON==57 | BUTTON==48)
        maptest=0;
        scattertest=0;
        [obs,affc]=selectstat('scatter',obs,var1,'class',var2,BUTTON,Hbutt,vectclass,affc);
    end;
    
    
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        if maptest==0      
            maptest=1;
            scattertest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2 & BUTTON~=49 & BUTTON~=50 & BUTTON~=51 & BUTTON~=52 & BUTTON~=53 & BUTTON~=54 & BUTTON~=55 & BUTTON~=56 & BUTTON~=57 & BUTTON~=48 & BUTTON~=28 & BUTTON~=29 &BUTTON~=30 & BUTTON~=31 & BUTTON~=105 & BUTTON~=106 & BUTTON~=107 & BUTTON~=108
            if ~isempty(find(affc==1))
                obs=zeros(size(long,1),1);
                for i=1:nbc
                    set(Hbutt(i),'Value',0);
                end;
                affc=zeros(nbc,1);
            end;
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');   
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            if ~isempty(find(affc==1))
                obs=zeros(size(long,1),1);
                for i=1:nbc
                    set(Hbutt(i),'Value',0);
                end;
                affc=zeros(nbc,1);
            end;
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        end;
        %%%%%%%%%%%%%%%%%%%
    %%%%%%%%%%%%%%%%%%%%%%%
    % scatterplot selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        cpa=get(Axis2,'CurrentPoint');
        if scattertest==0
            scattertest=1;
            maptest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2 & BUTTON~=49 & BUTTON~=50 & BUTTON~=51 & BUTTON~=52 & BUTTON~=53 & BUTTON~=54 & BUTTON~=55 & BUTTON~=56 & BUTTON~=57 & BUTTON~=48 & BUTTON~=28 & BUTTON~=29 &BUTTON~=30 & BUTTON~=31 & BUTTON~=105 & BUTTON~=106 & BUTTON~=107 & BUTTON~=108
            if ~isempty(find(affc==1))
                obs=zeros(size(long,1),1);
                for i=1:nbc
                    set(Hbutt(i),'Value',0);
                end;
                affc=zeros(nbc,1);
            end;
            obs=selectstat('scatter3d',obs,var1,var2,var3,cpa);
        %%%%%%%%%%%%%%%%%%
        end;
        %%%%%%%%%%%%%%%%%%%%
    end;
    %%%%%%%%%%%%%%%%%%%%%%
end;
out=obs;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%